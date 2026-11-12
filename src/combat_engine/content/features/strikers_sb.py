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
* **A fork read off the secondary ability.** `chargen.BUILDS` derives a
  leg per secondary for the classes phase C brought in, and the printed
  fork for the assassin and the monk *is* a choice of which secondary the
  class leans on -- each option's benefit reads the ability its leg is
  named for. The avenger's legs are hand-written and named, and the same
  correspondence picks which named leg each option is. It is a judgement
  either way, recorded in each docstring.
* **"You gain <power>".** `chargen.loadout` deals every level-0 row of a
  class, so the grant is a no-op and only the exclusivity is worth saying.
  Where the printed page does not say which option a leg took, nothing is
  taken away -- see `cf:barbarian-f1` and `docs/blocked.json`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.builds import on_leg

#: The label `p12660` lays its aura under, imported rather than repeated.
#: Two berserker rows ask about that aura -- `-f0` ends it and `-f2` reads
#: it live -- and a copy of the string here would go stale the day the
#: fighter's row renames it.
from combat_engine.content.powers.fighter.level_0 import AURA as DEFENDER_AURA
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Gear,
    Keyword,
    When,
    distance,
    get,
    power,
)
from combat_engine.engine.basic import MELEE
from combat_engine.engine.events import AttackDeclared, Dropped, Hit, Moved
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
    "cf:barbarian-f0",
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
    "cf:barbarian-f1",
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
    "cf:barbarian-f3",
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


# ----------------------------------------------- barbarian: the berserker
#
# The second chassis this class prints, and the one the four rows above are
# the `original` of. It is a defender that stops being one: the chassis
# carries `p12660`'s aura and the opportunity row that guards it, and the
# fury trades both away for damage. So two of its six rows exist only to
# turn the other two off, which is why the fury does the forbidding rather
# than each aura row refusing itself.
#
# Every row carries `on_leg("berserker")`. `chargen.BUILDS["barbarian"]`
# already held a leg of that name before any of this was written, so the
# chassis and the leg are the same choice -- and the header is what
# `chargen.legs_for` reads to keep the other four legs off this chassis.

#: The label the fury stands under. Public, because the printed *"some of
#: your powers ... gain additional benefits, as noted in those powers"*
#: puts the reading half in those powers rather than here -- `#550`'s
#: arrangement for a feat that names a power, applied to a chassis.
FURY = "cf:barbarian-berserker-fury"

#: The two rows the fury takes off the board for as long as it stands: the
#: aura `-f1` grants and the opportunity row `-f3` names.
_FURY_FORBIDS = ("p12660", "p15848")


def _a_melee_basic(ctx: dict[str, Any]) -> bool:
    """"Your melee basic attacks deal 1d8 extra damage."

    `MELEE` and not a literal, and melee only: `basic.RANGED` is its own
    word, so a ranged basic attack asks a different question and this
    clause is not about it.
    """
    return ctx.get("power") == MELEE


def _a_weapon_attack(ctx: dict[str, Any]) -> bool:
    """"Any weapon attack you make" -- the keyword on the row that is
    rolling, read off the damage context.

    Written locally rather than imported from `primal_divine._weapon_row`,
    which is the same three lines: that file imports `on_leg` and this one
    now does too, and a sideways import between two feature modules for a
    keyword test is a cycle waiting to be introduced by the next reader.
    """
    rolling = get(ctx.get("power") or "")
    return rolling is not None and Keyword.WEAPON in rolling.keywords


def _heartland_resist(c: Cast, dtype: DamageType) -> None:
    """"At 4th level, you gain resist 5 <element>. The resistance increases
    to 10 at 14th level and 15 at 24th level."

    Two of the three heartlands print this ladder and it is **not**
    `_tier`'s: that one steps at 11 and 21, this one at 4, 14 and 24. They
    were written as the same function for one draft, which paid a level-11
    berserker 10 where the card says 5.
    """
    if c.level < 4:
        return
    amount = 5 * (1 + (c.level >= 14) + (c.level >= 24))
    c.resist(amount, dtype, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:barbarian-berserker-f0",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
    dropped=("actions.offer_trait(requires=bloodied)",),
)
def berserker_fury(c: Cast) -> None:
    """The fury, which a berserker enters by attacking and cannot leave.

    A trait that lays a **watch**, not a trait that lays modifiers: the
    printed fury starts at a moment and the whole card is what happens
    then. `AttackDeclared` is the event -- *"when you use a barbarian
    primal attack power"* is asked of the row being used, so the gate reads
    `get(ev.power)` for the class, the keyword and `is_attack` rather than
    guessing from the name.

    **Latched on its own label rather than on a dict.** The fury stands
    until the end of the encounter, so every later primal attack re-enters
    it; without the guard each one would lay another `1d8` and forbid the
    same two rows again. `c.lingers_label` reads the hold off the world,
    which is the rule `content/CLAUDE.md` gives for exactly this and the
    reason ten rows keyed on `id(c.world)` were wrong.

    **The forbidding lives here, not in the two rows it silences.** Both
    of those are legitimate until the fury starts, and a row that refuses
    itself cannot say *"until the fury ends"*; `c.forbid` with the fury's
    own duration can. `c.end_effect(against=DEFENDER_AURA)` is the
    *"ends, if it was active"* half -- the aura is a labelled hold, so
    naming the label is how it is found, and `against=` matching nothing
    is the "if it was active" the card prints.

    **What is dropped is the second way in**, and it is not redundant with
    the first. *"Alternatively, you can use a minor action while you are
    bloodied"* matters because the berserker's martial at-will attacks are
    **not** primal, so a berserker who swings only those never enters the
    fury automatically -- and the choice is a real one, since entering it
    costs the aura and the guardian row. That needs the trait to be
    offerable on the action menu, which `turns.arm_traits` cannot do for an
    `action=NONE` row, so the symbol names the offer rather than the
    bloodied test (`c.bloodied` already exists).

    The *"some of your powers ... gain additional benefits"* sentence owes
    this row nothing: it is a pointer, and `FURY` above is what those
    powers read. Whether they do is `#1260`.
    """
    me = c.me
    dice = 1 + _tier(c.level)

    def enter(ev: AttackDeclared) -> None:
        if ev.attacker != me or c.lingers_label(FURY, on=me):
            return
        declared = get(ev.power)
        if declared is None or declared.cls != "barbarian":
            return
        if not declared.is_attack or Keyword.PRIMAL not in declared.keywords:
            return
        c.effect(FURY, until=When.ENCOUNTER, on=me)
        c.end_effect(against=DEFENDER_AURA, on=me)
        for ref in _FURY_FORBIDS:
            c.forbid(ref, on=me, until=When.ENCOUNTER)
        c.bonus("damage", 0, dice=f"{dice}d8", on=me, until=When.ENCOUNTER,
                when=_a_melee_basic)

    c.watch(AttackDeclared, enter, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:barbarian-berserker-f1",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_defender_aura(c: Cast) -> None:
    """"You gain the p12660 power."

    **This grant is load-bearing, which most of its kind are not.**
    `chargen.loadout` hands a character every level-0 row of *its own
    class*, and `p12660` is declared `cls="fighter"` -- the Essentials
    defenders share one aura and the fighter's page printed it first. So a
    barbarian is not dealt it and `c.grant_row` is the only thing that
    puts it in reach. Compare `-f3` below, which grants a barbarian row and
    is therefore the no-op the file's header describes.
    """
    c.grant_row("p12660", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:barbarian-berserker-f2",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_defender_ac(c: Cast) -> None:
    """"While your p12660 is active and you're not wearing heavy armor, you
    gain a +2 bonus to AC."

    **Two gates read at two different times, deliberately.** The armour is
    read once when the trait arms, as every other row in this file does and
    for the same reason -- nothing in a fight changes what is worn. The
    aura is read **live**, in a `when=`, because it is a minor-action power
    that goes up and down and the fury takes it away mid-fight; measuring
    it at arming would pay a berserker the +2 for a whole encounter in
    which the aura never went up.
    """
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in HEAVY:
        return
    me = c.me
    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: c.lingers_label(DEFENDER_AURA, on=me))


@power(
    "cf:barbarian-berserker-f3",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_guardian(c: Cast) -> None:
    """"You gain the p15848 power."

    A no-op grant: `p15848` is declared `cls="barbarian"` at level 0, so
    `chargen.loadout` has already dealt it and `c.grant_row` returns
    `None`. Written out anyway, because the row is what `-f0` forbids and a
    reader following that `c.forbid` needs to land somewhere.
    """
    c.grant_row("p15848", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:barbarian-berserker-f4",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_heartland(c: Cast) -> None:
    """*"You choose one of the following terrain types that best represents
    your heartland and gain its benefit."*

    A **parent**, so `chargen.ladder_row` deals it and it picks among its
    own three options -- `chargen.BUILD_OPTIONS` and not a leg, because the
    leg is already spent: `berserker` *is* this chassis. The same split the
    witch's coven records, arrived at from the other direction.

    All three options are declared below, so this grants rather than
    repeating what they say.
    """
    land = c.chosen_option("cf:barbarian-berserker-f4") or "cf:barbarian-berserker-f4s0"
    c.grant_row(land, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:barbarian-berserker-f4s0",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_heartland_robed(c: Cast) -> None:
    """One heartland: +3 AC and +2 Reflex out of armour, and fire resistance
    from 4th level.

    `_in_a_robe` is the file's own reading of *"wearing cloth armor or no
    armor and not using a shield"*, shared with the monk's defence row.
    Two calls rather than one, because AC and Reflex are separate keys and a
    single `c.bonus` would have paid only one of them -- the mistake
    `cf:barbarian-f0` records at the top of this file.

    The resistance is **not** gated on the robe. The card prints the armour
    requirement in front of the two bonuses and starts a new sentence for
    the resistance, so a berserker of this heartland in plate keeps it.
    """
    if _in_a_robe(c):
        c.bonus(AC, 3, on=c.me, until=When.ENCOUNTER, kind="untyped")
        c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="untyped")
    _heartland_resist(c, DamageType.FIRE)


@power(
    "cf:barbarian-berserker-f4s1",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_heartland_hardy(c: Cast) -> None:
    """One heartland: +1 Fortitude and Will, and cold resistance from 4th.

    The one option of the three that gates on nothing -- no armour clause,
    no weapon clause -- so it is the control for the other two: if the
    heartland fork itself ever stopped being dealt, this row is the one
    that would go silent with no gate to blame.
    """
    c.bonus(FORT, 1, on=c.me, until=When.ENCOUNTER, kind="untyped")
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER, kind="untyped")
    _heartland_resist(c, DamageType.COLD)


@power(
    "cf:barbarian-berserker-f4s2",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("berserker"),
)
def berserker_heartland_shielded(c: Cast) -> None:
    """One heartland: +2 damage with a one-handed weapon behind a shield, and
    a charging bonus from 4th level.

    *"The damage rolls of any weapon attack you make with that weapon"* --
    "that weapon" is the one-handed one in the main hand, and the shield is
    what makes the off hand unavailable, so every weapon attack this
    character makes is with it. The gate is therefore the weapon test and
    not a hand test; `primal_divine.py` needs `ctx["hand"]` because a
    two-weapon fighter has a choice and this berserker does not.

    The speed bonus reads `ctx["charge"]`, which is `p4887`'s gate and the
    only thing that distinguishes a charge from a walk -- `query.charging`
    answers about the creature and is the wrong half here, because a
    modifier is asked about the move being priced.
    """
    gear = c.world.get(c.me, Gear)
    main = gear.main if gear is not None else None
    if gear is None or not gear.shield or main is None:
        return
    if "one-handed" not in main.properties:
        return
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack)
    if c.level >= 4:
        c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
                when=lambda ctx: bool(ctx.get("charge")))


# ----------------------------------------------------------------- avenger


@power(
    "cf:avenger-f0",
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
    "cf:avenger-f1",
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

    Three are printed and two are written, one per leg of
    `chargen.BUILDS["avenger"]`. This asked `c.build("second-dex")` and
    `c.build("second-int")` -- the derived legs the class no longer has --
    so both halves were false for every avenger and no avenger had a
    censure at all. The named legs answer it: the one whose secondary is
    Dexterity is the option whose bonus is worked out from Dexterity, and
    likewise for Intelligence. That correspondence is a judgement and not a
    printed sentence, which is why it is said here.

    The third option counts allies standing next to the sworn enemy and
    reads no ability at all, which is why it could not be told apart from
    either of the other two while the legs were derived. It has a leg of
    its own now, and `cf:avenger-f1s2` in `features/primal_divine.py`
    gates on it.

    Both bonuses are untyped and so both stack, which is what the second
    one's "this bonus is cumulative" says outright. The gate asks who the
    oath is on at the moment the damage is rolled rather than closing over
    a creature, because half a dozen rows in the class re-swear mid-fight.
    """
    from combat_engine.content.powers.avenger.oath import sworn

    me, world = c.me, c.world

    def against_the_sworn(ctx: dict[str, Any]) -> bool:
        return sworn(world, me, ctx.get("target"))

    if c.build("pursuit"):
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

    if not c.build("retribution") or c.int_mod <= 0:
        return

    def struck(ev: Hit) -> None:
        if ev.target != me or ev.attacker == me:
            return
        if team(world, ev.attacker) is team(world, me):
            return
        # "Any enemy **other than** your sworn target" -- `cf:avenger-f3`.
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
    "cf:assassin-f1",
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
    that secondary -- the same correspondence `cf:avenger-f1`
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
    if not c.build("f1s0"):
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
    "cf:monk-f2",
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
    "cf:monk-f0",
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
    if c.build("f0s0"):
        c.bonus(FORT, 1 + _tier(c.level), until=When.ENCOUNTER, on=c.me, kind="untyped")
