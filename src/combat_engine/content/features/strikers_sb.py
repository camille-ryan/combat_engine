"""The striker class-page features nothing in the tree recorded at all.

Five classes here, and each one is a feature that had no implementation, no
`Feature` power row and no `docs/blocked.json` entry -- so nothing anywhere
counted it as absent and every class read as finished. They are written from
the imported class pages, which `scripts/spec.py --class <name> --features`
prints for the first time.

Three shapes recur:

* **Armour as a gate.** Three of the eight classes pay a standing defence
  bonus for wearing little or nothing. `chargen.defences` works out the
  armour's own contribution and knows nothing about class features, so each
  of these is a real number the character was missing.
* **A fork with no leg of its own.** `chargen.BUILDS` derives a leg per
  secondary ability for the classes phase C brought in, and the printed
  fork for the avenger, the assassin and the monk *is* a choice of which
  secondary the class leans on -- each option's benefit reads the ability
  its leg is named for. That correspondence is the mapping used here and
  it is a judgement, recorded in each docstring.
* **"You gain <power>".** `chargen.loadout` deals every level-0 row of a
  class, so the grant is a no-op and only the exclusivity is worth saying.
  Where the printed page does not say which option a leg took, nothing is
  taken away -- see `cf:barbarian-might` and `docs/blocked.json`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    ActionType,
    Cast,
    Gear,
    Keyword,
    When,
    distance,
    get,
    power,
)
from combat_engine.engine.events import Dropped, Hit, Moved
from combat_engine.engine.query import team

#: The armours "while you are not wearing heavy armor" rules out. Named
#: rather than inverted from `chargen.LIGHT`, because that is the printed
#: wording and the two lists are maintained on different pages.
HEAVY = ("chain", "scale", "plate")

#: "While you are wearing cloth armor or no armor": the empty string is what
#: a creature with no `Gear` armour field set is wearing.
BARE = ("", "cloth")

#: The `Moved.kind_` words that are somebody else doing the moving. A
#: teleport is not here: a creature that teleports away did it itself.
FORCED = ("push", "pull", "slide")


def _in_a_robe(c: Cast) -> bool:
    """"Wearing cloth armor or no armor and not using a shield"."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return True
    return not gear.shield and gear.armour in BARE


def _tier(level: int) -> int:
    """0, 1 or 2 -- the step every one of these ladders climbs at 11 and 21."""
    return (level >= 11) + (level >= 21)


# --------------------------------------------------------------- barbarian


@power(
    "cf:barbarian-agility",
    level=0,
    cls="barbarian",
    # A trait: it is simply true of a barbarian who is not in heavy plate,
    # and `Encounter._arm_traits` turns it on when the fight starts.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def barbarian_agility(c: Cast) -> None:
    """Out of heavy armour, a barbarian is harder to hit and harder to catch.

    Two bonuses rather than one, because AC and Reflex are separate keys and
    a single call would have paid only one of them. Untyped: the card prints
    no type word, and `c.bonus` unspecified is untyped anyway -- it is
    written out because the other half of the pair is, and a reader
    comparing the two should not have to check.

    The armour is read once, when the trait arms. Nothing in a fight changes
    what a character is wearing, so a gate re-asked on every roll would cost
    the same answer every time.
    """
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in HEAVY:
        return
    step = 1 + _tier(c.level)
    c.bonus(AC, step, until=When.ENCOUNTER, on=c.me, kind="untyped")
    c.bonus(REF, step, until=When.ENCOUNTER, on=c.me, kind="untyped")


#: The row the one printed option of the barbarian's fork hands over: the
#: free action, on dropping an enemy, whose whole Effect is a charge.
_RAGEBLOOD_ROW = "p4809"


@power(
    "cf:barbarian-might",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def barbarian_might(c: Cast) -> None:
    """The class's fork, of which the compendium imported exactly one option.

    That option is a granted row and a rider. The row is the free action
    that charges when an enemy goes down -- `chargen.loadout` has already
    dealt it, so `c.grant_row` returns `None` and the sentence is only worth
    writing on the *other* leg, which loses it. The rider is the half with
    content: vitality off every kill.

    **The other three options are not taken away from this leg**, and that
    is deliberate rather than an oversight. Four rows on this class answer
    the same printed trigger and are plainly the four options' granted
    powers, but only one option's text is on the imported page, so which of
    the remaining three belongs to the other leg cannot be said. Forbidding
    all three here would take three working rows off the board to express
    half a sentence. `docs/blocked.json` carries it.
    """
    me = c.me
    if not c.build("rageblood"):
        # `c.forbid` follows `c.target` and a trait has none.
        c.forbid(_RAGEBLOOD_ROW, until=When.ENCOUNTER, on=me)
        return
    c.grant_row(_RAGEBLOOD_ROW)
    amount = c.con_mod + 5 * _tier(c.level)

    def on_drop(ev: Dropped) -> None:
        if ev.source != me or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        c.temp_hp(amount, on=me)

    c.watch(Dropped, on_drop, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:barbarian-rampage",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def barbarian_rampage(c: Cast) -> None:
    """A critical hit with one of this class's attacks buys a free swing.

    `Hit.critical` is a declared field, so the condition is read off the
    event rather than asked of the result afterwards. The row that caused it
    has to be one of this class's -- which keeps the free swing from
    triggering itself, since a basic attack is classless.

    "You do not have to attack the same target": the choice is offered over
    everyone in reach, and declining is one of the answers, because the card
    says *can*. Once a round, latched before the swing is made so a critical
    basic attack cannot re-enter.
    """
    me = c.me
    paid: dict[int, int] = {}

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or not ev.critical:
            return
        declared = get(ev.power)
        if declared is None or declared.cls != "barbarian" or not declared.is_attack:
            return
        if paid.get(me) == c.world.round:
            return
        reachable = [foe for foe in c.enemies() if c.adjacent(foe)]
        if not reachable:
            return
        paid[me] = c.world.round
        victim = c.choose(reachable, f"{c.ref}: who to swing at", optional=True)
        if victim is not None:
            c.basic(on=victim)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=c.ref)


# ----------------------------------------------------------------- avenger


@power(
    "cf:avenger-faith",
    level=0,
    cls="avenger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def avenger_faith(c: Cast) -> None:
    """Three points of AC for going into a fight in a robe and no shield.

    `chargen.defences` already gives cloth the better of Dexterity and
    Intelligence, which is the *armour's* contribution; this is the class's,
    and the chassis was carrying neither half of the page until now.
    """
    if _in_a_robe(c):
        c.bonus(AC, 3, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:avenger-censure",
    level=0,
    cls="avenger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def avenger_censure(c: Cast) -> None:
    """Which way this avenger punishes the enemy it has sworn against.

    Three are printed and two are written. Each reads a different ability,
    and `chargen.BUILDS["avenger"]` is the derived pair of legs named for
    the secondary each takes -- so the leg that leans on Dexterity is the
    option whose bonus is worked out from Dexterity, and likewise for
    Intelligence. That is the correspondence the derived legs exist to
    express; it is a judgement and not a printed sentence, which is why it
    is said here.

    The third option counts allies standing next to the sworn enemy and
    reads no ability at all, so there is no leg it could be told apart by.
    See `docs/blocked.json`.

    Both bonuses are untyped and so both stack, which is what the second
    one's "this bonus is cumulative" says outright. The gate asks who the
    oath is on at the moment the damage is rolled rather than closing over
    a creature, because half a dozen rows in the class re-swear mid-fight.
    """
    from combat_engine.content.powers.avenger.oath import sworn

    me, world = c.me, c.world

    def against_the_sworn(ctx: dict[str, Any]) -> bool:
        return sworn(world, me, ctx.get("target"))

    if c.build("second-dex"):
        step = 2 + 2 * _tier(c.level) + c.dex_mod

        def fled(ev: Moved) -> None:
            if ev.actor == me or not sworn(world, me, ev.actor):
                return
            if getattr(ev, "kind_", "") in FORCED:
                return
            # "Moves away from you": measured, because a sworn enemy
            # circling at the same distance has not moved away.
            if distance(c.here, ev.to) <= distance(c.here, ev.from_):
                return
            # `stacks=False`, and it is the difference between +4 and +12:
            # a walk emits one `Moved` per square, and this option -- unlike
            # the other, which says "cumulative" outright -- grants one
            # bonus for moving away, however far.
            c.bonus(
                "damage", step, until=When.EONT, on=me,
                stacks=False, when=against_the_sworn,
            )

        c.watch(Moved, fled, until=When.ENCOUNTER, on=me, label=c.ref)
        return

    if not c.build("second-int") or c.int_mod <= 0:
        return

    def struck(ev: Hit) -> None:
        if ev.target != me or ev.attacker == me:
            return
        if team(world, ev.attacker) is team(world, me):
            return
        # "Any enemy **other than** your oath of enmity target."
        if sworn(world, me, ev.attacker):
            return
        c.bonus(
            "damage", c.int_mod, until=When.EONT, on=me, kind="untyped",
            when=against_the_sworn,
        )

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=c.ref)


# ---------------------------------------------------------------- assassin

#: The row the second of the two printed methods hands over: the free
#: encounter rider that adds a die to a weapon hit within 5 squares.
_EXECUTIONER_ROW = "p14372"


@power(
    "cf:assassin-training",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def assassin_training(c: Cast) -> None:
    """Hitting somebody who is still whole feeds the assassin.

    Two methods are printed and the class has exactly two legs, so each is
    identified. This one reads Constitution and rides the leg named for
    that secondary -- the same correspondence `cf:avenger-censure`
    explains. The other's first clause is a granted row, which
    `chargen.loadout` has already dealt, so the half worth writing is that
    *this* leg does not have it. Its second clause -- the loss of every
    encounter attack power in the class -- is not sayable a ref at a time
    and `docs/blocked.json` carries it.

    `Hit` is announced before the damage lands, so "an unbloodied target" is
    the state the sentence means -- the blow that bloodies a creature still
    pays. Temporary hit points do not stack, so a second hit in the same
    round renews rather than adds, which is the printed rule and not a
    limitation of this row.
    """
    me = c.me
    if not c.build("second-con"):
        return
    # `c.forbid` follows `c.target`, and a trait has none.
    c.forbid(_EXECUTIONER_ROW, until=When.ENCOUNTER, on=me)
    amount = c.con_mod + 2 * _tier(c.level)
    if amount <= 0:
        return

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or ev.target == me:
            return
        if c.bloodied(on=ev.target):
            return
        c.temp_hp(amount, on=me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=c.ref)


# -------------------------------------------------------------------- monk


@power(
    "cf:monk-defence",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
)
def monk_defence(c: Cast) -> None:
    """Two points of AC for fighting in a robe with both hands free.

    The rest of the printed section is the one-full-discipline-power-a-round
    budget, which is a per-*round* allowance across a set of rows where
    `group=` is per encounter. It is in `docs/blocked.json`.
    """
    if _in_a_robe(c):
        c.bonus(AC, 2, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:monk-tradition",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
)
def monk_tradition(c: Cast) -> None:
    """The tradition's defensive half, for the one tradition the page prints.

    A tradition is a granted attack row and a standing defence bonus. Only
    one of the two named traditions has its benefit on the imported page --
    a step of Fortitude -- and it belongs to the leg that leans on Wisdom.

    The granted rows are the harder half and are not touched here: the class
    has five of them in the tree and two named traditions, so four of the
    five cannot be assigned to a leg at all. `docs/blocked.json` carries it.
    """
    if c.build("second-wis"):
        c.bonus(FORT, 1 + _tier(c.level), until=When.ENCOUNTER, on=c.me, kind="untyped")
