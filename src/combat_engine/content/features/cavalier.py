"""The cavalier, the paladin's third chassis.

`#642`'s wave. 34 printed rows, and structurally the blackguard again: a
**virtue** chosen once and read by four parents (`-f4`, `-f6`, `-f10`,
`-f14`), with one `chargen.BUILD_OPTIONS` entry and three readers of it.
`features/blackguard.py` has the argument at length and it is not repeated
here; what is repeated is the shape, deliberately, so the two chassis read
the same and `drivers.cavalier_virtue` can assert the same property.

The shape:

    14  play
     2  another use of `p13553` per encounter
     2  self-referential grants -- `defect=`
     8  "one of the following powers" and no list -- `defect=`
     1  a power naming itself by a composite -- `defect=`
     1  a mount's speed, explicitly out of combat

## Nine grants and only three are no-ops

    -f0   p12660   cls="FIGHTER", level 0  -> real
    -f1   p13553   cls="paladin", level 0  -> no-op
    -f2   p13554   cls="paladin", level 0  -> no-op
    -f3   p13555   cls="paladin", level 0  -> no-op
    -f5   p835     cls="paladin", level 1  -> in the draw
    -f6s0 p13575   cls="paladin", level 1  -> in the draw
    -f6s1 p13580   cls="paladin", level 1  -> in the draw
    -f7   p13557   cls="paladin", level 2  -> real
    -f11  p13561   cls="paladin", level 8  -> real

Three categories, which is what the scout's three grants established and
this chassis exercises nine times: a level-0 row of the class is always
dealt, a row above the character's level never is, and a row **at** its
level is inside the draw and may be either. `-f0` is the fourth case --
another class's row entirely, the Essentials defender aura the knight and
the berserker also carry.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    DamageType,
    Keyword,
    When,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.events import PowerResolved, SurgeSpent
from combat_engine.engine.query import team

#: The one row the virtue is chosen on. Three other parents read this ref
#: rather than carrying entries of their own -- `features/blackguard.py`
#: has the argument and `drivers.cavalier_virtue` asserts it holds.
VIRTUE = "cf:paladin-cavalier-f4"

#: The two virtues, in the order `BUILD_OPTIONS` lists them.
VIRTUES = ("cf:paladin-cavalier-f4s0", "cf:paladin-cavalier-f4s1")

#: The row `-f10`'s extra effect and `-f15`'s teleport both answer.
CHANNEL = "p13555"


def _virtue(c: Cast) -> int:
    """Which virtue this cavalier took: 0 or 1.

    One reader, asking about `VIRTUE` whoever is calling -- the same
    arrangement `features/blackguard.py::_vice` records, and for the same
    reason: four independent draws would make a character half of each
    virtue and nothing would notice.
    """
    chose = c.chosen_option(VIRTUE) or VIRTUES[0]
    return 1 if chose == VIRTUES[1] else 0


def _grant(ref: str, got: str, why: str) -> Any:
    """One of the nine "you gain <power>" rows.

    `why` is the measurement rather than a template, because on this
    chassis the nine answers come from four different reasons and a reader
    needs to see which applies.
    """

    @power(
        ref,
        level=0,
        cls="paladin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "cavalier_grant_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f'"You gain the `{got}` power."\n\n{why}'
    return row


cavalier_grant_0 = _grant(
    "cf:paladin-cavalier-f0", "p12660",
    "**A real grant, and the class is why.** `p12660` is "
    '`cls="fighter"` -- the Essentials defenders share one aura and the '
    "fighter's page printed it first -- so `loadout` deals it to a fighter "
    "and not to a paladin. `cf:fighter-knight-f1` grants this same ref as "
    "a no-op and `cf:barbarian-berserker-f1` as a real one, which makes "
    "three chassis on the same sentence with two different answers.")
cavalier_grant_1 = _grant(
    "cf:paladin-cavalier-f1", "p13553",
    "A no-op grant: a level-0 paladin row, already dealt. `#1259`.")
cavalier_grant_2 = _grant(
    "cf:paladin-cavalier-f2", "p13554",
    "A no-op grant: a level-0 paladin row, already dealt. `#1259`.")
cavalier_grant_3 = _grant(
    "cf:paladin-cavalier-f3", CHANNEL,
    "A no-op grant: a level-0 paladin row, already dealt -- and the row "
    "`-f10`'s two options and `-f15` are all about. `#1259`.")
cavalier_grant_5 = _grant(
    "cf:paladin-cavalier-f5", "p835",
    "**In the draw.** A level-1 paladin power at a level-1 character is "
    "inside `loadout`'s pool, so whether this grant matters depends on the "
    "hand -- the third category `drivers.blackguard_vice` had to be "
    "rewritten to see.")
cavalier_grant_7 = _grant(
    "cf:paladin-cavalier-f7", "p13557",
    "**A real grant, and the level is why.** Level 2 is above a level-1 "
    "character, so the draw cannot reach it.")
cavalier_grant_11 = _grant(
    "cf:paladin-cavalier-f11", "p13561",
    "**A real grant.** Level 8, far above the draw.")


@power(
    VIRTUE,
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_virtue(c: Cast) -> None:
    """*"You gain a benefit associated with your virtue."*

    **The one parent that carries the choice.** `-f6`, `-f10` and `-f14`
    read this row's answer rather than drawing their own.
    """
    c.grant_row(VIRTUES[_virtue(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:paladin-cavalier-f4s0",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("actions.offer_trait(second_wind_as_minor)",),
)
def cavalier_virtue_valour(c: Cast) -> None:
    """One virtue: an extra healing surge, and a second wind spent on an
    ally instead of yourself.

    The surge **is** written -- `Health.max_surges` and `Health.surges`
    both move, because granting a surge the creature cannot spend is half
    a clause. Written on the component rather than through a verb because
    there is none: `c.regain_surge` hands a spent one back and
    `c.spend_surge` takes one, and neither raises the allowance.

    Dropped: *"you can use your second wind as a minor action to heal an
    ally of your choice within 5 squares."* `c.second_wind(cost=)` already
    takes the action, so the **cost** is sayable -- what is not is putting
    a second, differently-priced version of an existing row on the action
    menu for the player to choose between. `cf:barbarian-berserker-f0` and
    `cf:paladin-blackguard-f3s0` wait on the same facility.

    The row plays, so `dropped=` and not `todo=`.
    """
    health = c.world.get(c.me, Health)
    if health is None:
        return
    health.max_surges += 1
    health.surges += 1


@power(
    "cf:paladin-cavalier-f4s1",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("Health.surge_bonus",),
)
def cavalier_virtue_zeal(c: Cast) -> None:
    """The other virtue: +4 to initiative, and a surge worth 2 more.

    **`c.initiative`, not `c.bonus("initiative", ...)`** --
    `Initiative.bonus` is summed before the d20 and `Mods` is never
    consulted, so the modifier would be laid and no roll would read it.
    `cf:rogue-thief-f11` records the measurement and `#1262` is why a row
    whose whole content is this reads SILENT; this one has a second clause
    marked beside it, so the verdict here is about the marker.

    Dropped: *"your healing surge value increases by 2."* `c.surge_value`
    is the **reader** and computes a quarter of maximum hit points with
    nothing added to it -- there is no field for a flat increase, and
    `Health` carries none. One symbol, naming the field the reader would
    have to consult rather than the clause.
    """
    c.initiative(4, on=c.me)


@power(
    "cf:paladin-cavalier-f6",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_virtue_attack(c: Cast) -> None:
    """*"You gain an at-will attack power associated with your virtue."*

    A parent with no choice of its own: it reads `VIRTUE`'s answer. Both
    options are declared below and both are level-1 paladin powers, so
    both are **inside the draw** -- the grant matters or not depending on
    the hand.
    """
    which = ("cf:paladin-cavalier-f6s0", "cf:paladin-cavalier-f6s1")
    c.grant_row(which[_virtue(c)], on=c.me, until=When.ENCOUNTER)


cavalier_grant_6s0 = _grant(
    "cf:paladin-cavalier-f6s0", "p13575",
    "**In the draw**, like `-f5`: a level-1 paladin power at a level-1 "
    "character.")
cavalier_grant_6s1 = _grant(
    "cf:paladin-cavalier-f6s1", "p13580",
    "**In the draw**, like its sibling.")


@power(
    "cf:paladin-cavalier-f10",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_virtue_channel(c: Cast) -> None:
    """*"Your p13555 power gains an additional effect associated with your
    virtue."*

    A parent reading `VIRTUE`'s answer, like `-f6`. Both options are
    declared below and both watch `p13555` resolving.
    """
    which = ("cf:paladin-cavalier-f10s0", "cf:paladin-cavalier-f10s1")
    c.grant_row(which[_virtue(c)], on=c.me, until=When.ENCOUNTER)


def _channel_rider(ref: str, what: str) -> Any:
    """One of `-f10`'s two extra effects on `p13555`.

    Both scale at 23rd level, and the step is **written** rather than
    marked: it is a number inside one clause, which the card prints in the
    same sentence, not a separate feature row superseding a lower one.
    `#1261`'s line is about the second kind, and
    `features/blackguard.py::_channel_rider` draws the same distinction.
    """

    @power(
        ref,
        level=0,
        cls="paladin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        me = c.me

        def rider(ev: PowerResolved) -> None:
            if getattr(ev, "actor", None) != me:
                return
            if getattr(ev, "power", "") != CHANNEL:
                return
            if ref.endswith("s0"):
                # "The damage you take is reduced by 10" -- a standing
                # reduction for as long as the channel's own effect runs,
                # not a one-off `c.reduce`: that verb answers a blow that
                # has been rolled and this clause is laid before any.
                c.resist(20 if c.level >= 23 else 10, until=When.EONT, on=me)
                return
            amount = (5 if c.level >= 23 else 2) + c.cha_mod
            c.bonus("damage", amount, on=me, until=When.EONT,
                    kind="untyped", once=True)

        c.watch(PowerResolved, rider, until=When.ENCOUNTER, on=me,
                label=c.ref)

    row.__name__ = "cavalier_channel_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One virtue's extra effect on `{CHANNEL}`: {what}.\n\n"
        "`PowerResolved` and not a declared trigger, because the row is a "
        "standing fact about what `p13555` now does rather than something "
        "the cavalier answers. `once=True` on the damage half is *\"your "
        "next damage roll\"* -- spent by the first roll that reads it."
    )
    return row


cavalier_channel_0 = _channel_rider(
    "cf:paladin-cavalier-f10s0", "damage taken is reduced")
cavalier_channel_1 = _channel_rider(
    "cf:paladin-cavalier-f10s1", "a bonus to the next damage roll")


@power(
    "cf:paladin-cavalier-f13",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_succour(c: Cast) -> None:
    """"Whenever an ally adjacent to you spends a healing surge, he or she
    gains temporary hit points equal to your Charisma modifier."

    **The ally gains them, not the cavalier**, which is the one thing to
    get right here: `cf:paladin-blackguard-f17` is the same trigger and
    the same number and the temporary hit points go the **other way**. Two
    chassis of one class, one sentence apart, and a `c.temp_hp` with the
    wrong `on=` would be invisible on either.

    The geometry is read when the surge is spent rather than when the trait
    arms, which is `cf:druid-protector-f0s0`'s reasoning for the same
    event: a party moves inside a fight.
    """
    me, world = c.me, c.world
    amount = c.cha_mod
    if amount <= 0:
        return

    def succour(ev: SurgeSpent) -> None:
        who = getattr(ev, "actor", None)
        if who is None or who == me:
            return
        if team(world, who) is not team(world, me):
            return
        if not c.adjacent(who):
            return
        c.temp_hp(amount, on=who)

    c.watch(SurgeSpent, succour, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:paladin-cavalier-f14",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_virtue_utility(c: Cast) -> None:
    """*"You gain a utility power associated with your virtue."*

    The fourth parent reading `VIRTUE`'s answer, and **both its options
    are `defect=`** -- so this row grants a row that refuses itself. The
    parent is not broken, its options are, and `usable` is what stops
    either reaching play. `cf:paladin-blackguard-f19` is the same case on
    the sibling chassis.
    """
    which = ("cf:paladin-cavalier-f14s0", "cf:paladin-cavalier-f14s1")
    c.grant_row(which[_virtue(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:paladin-cavalier-f15",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_charge(c: Cast) -> None:
    """"Immediately after you use your p13555, you can take a free action to
    teleport up to 5 squares to a square adjacent to the target."

    A `PowerResolved` watch, which is what *"immediately after you use"*
    means -- `cf:paladin-blackguard-f20` is the same sentence on the
    sibling chassis without the destination clause.

    **`toward=` is what makes "adjacent to the target" sayable.**
    `c.teleport` takes a creature to move toward, so the destination is
    expressed as the target rather than as a square -- and the victim
    comes off `PowerResolved.targets`, which is where a non-triggered row
    records who it hit.

    `who=` and not `on=`: `c.teleport` spells the creature `who`, as
    `c.shift` does and `c.slide` does not.
    """
    me = c.me

    def charge(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if getattr(ev, "power", "") != CHANNEL:
            return
        aimed = list(getattr(ev, "targets", ()) or ())
        if not aimed or not c.may("teleport to it"):
            return
        c.teleport(5, who=me, toward=aimed[0])

    c.watch(PowerResolved, charge, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:paladin-cavalier-f16",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def cavalier_inured(c: Cast) -> None:
    """"You gain resist 20 necrotic and resist 20 poison."

    Two calls, because `c.resist` takes one damage type.
    `cf:paladin-blackguard-f22` is the same clause with cold instead of
    poison, which is worth noticing: the two chassis print the pair that
    matches their flavour and share the shape.
    """
    for kind in (DamageType.NECROTIC, DamageType.POISON):
        c.resist(20, kind, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:paladin-cavalier-f9",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def cavalier_ride(c: Cast) -> None:
    """A mount's speed, and the card says outright that a fight has no use
    for it.

    *"While you are riding a mount, that creature and each allied mount
    within 20 squares of you gain a +2 power bonus to speed. **This bonus
    applies only outside combat.**"*

    `out_of_combat=True` is the marker the card writes for us -- the one
    row in this wave where the printed text names its own scope rather
    than leaving the reading to be argued. Empty rather than a `c.note`:
    a trait runs at the start of every fight and a line in the log would
    announce something that is not happening, which is `cf:druid-f2`'s
    reasoning.
    """


# -- the two that add a use of the channel -----------------------------------


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p13553` per
    encounter."""

    @power(
        ref,
        level=0,
        cls="paladin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        c.more_uses("p13553", 1, on=c.me)

    row.__name__ = "cavalier_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p13553` per encounter, still only once a turn.\n\n"
        "The same two gaps `cf:fighter-slayer-f3`, `cf:rogue-thief-f6` and "
        "`cf:paladin-blackguard-f7` name, and the same two symbols -- the "
        "level is `#1261`'s, and nothing raises an existing row's "
        "per-encounter ceiling."
    )
    return row


cavalier_extra_use_8 = _extra_use("cf:paladin-cavalier-f8")
cavalier_extra_use_12 = _extra_use("cf:paladin-cavalier-f12")


# -- the eleven rows the import cannot supply --------------------------------


def _defective(ref: str, why: str) -> Any:
    """A row whose printed text names something no ref resolves."""

    @power(
        ref,
        level=0,
        cls="paladin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "cavalier_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


_SELF = ("the spec reads 'you gain the {ref} power' -- the feature names "
         "itself as the power it grants, and no such ref exists")
_NO_LIST = ("the spec reads 'you gain one of the following powers of your "
            "choice' and then lists nothing, so there is no set to choose "
            "from")
_NO_LIST_SWAP = (_NO_LIST + ", and the new power is also meant to replace "
                 "a daily the character already has")

cavalier_defect_14s0 = _defective(
    "cf:paladin-cavalier-f14s0", _SELF.format(ref="cf:paladin-cavalier-f14s0"))
cavalier_defect_14s1 = _defective(
    "cf:paladin-cavalier-f14s1", _SELF.format(ref="cf:paladin-cavalier-f14s1"))
cavalier_defect_17 = _defective(
    "cf:paladin-cavalier-f17",
    "the spec reads 'you gain the avatar of p7249 power' -- a printed name "
    "with a ref embedded in it, and `p7249` is a level-2 paladin attack "
    "power rather than the epic daily the row means, so the importer "
    "resolved the wrong half of the phrase and the power itself has no ref")
cavalier_defect_18 = _defective("cf:paladin-cavalier-f18", _NO_LIST)
cavalier_defect_19 = _defective("cf:paladin-cavalier-f19", _NO_LIST)
cavalier_defect_20 = _defective("cf:paladin-cavalier-f20", _NO_LIST)
cavalier_defect_21 = _defective("cf:paladin-cavalier-f21", _NO_LIST)
cavalier_defect_22 = _defective("cf:paladin-cavalier-f22", _NO_LIST)
cavalier_defect_23 = _defective("cf:paladin-cavalier-f23", _NO_LIST)
cavalier_defect_24 = _defective("cf:paladin-cavalier-f24", _NO_LIST_SWAP)
cavalier_defect_25 = _defective("cf:paladin-cavalier-f25", _NO_LIST_SWAP)
