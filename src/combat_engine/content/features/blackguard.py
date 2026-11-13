"""The blackguard, the paladin's second chassis.

`#642`'s wave. 32 printed rows, the largest in the wave, and the one with a
structural problem none of the other eight had: **one choice read by four
different parents.**

## The vice is chosen once and asked about four times

`-f3`, `-f5`, `-f11` and `-f19` each print *"associated with your vice"* and
each has its own two sub-options. Four `chargen.BUILD_OPTIONS` entries
would be four **independent draws**, so a blackguard could hold the first
vice's benefit beside the second vice's at-will -- a character that is
half of each, which is `#851`'s fault arriving through a door the
sub-option clause does not cover.

So there is **one** entry, on `-f3`, and the other three parents read that
ref's answer: `c.chosen_option` takes a ref, so any row can ask what
another row chose. `VICE` below is the one place the ref is written and
`_vice(c)` is the one reader.

The cost of getting it wrong would have been silent -- every row works in
isolation and the character is simply incoherent -- which is why
`drivers.blackguard_vice` asserts all four parents agree on every seed
rather than that each one grants something.

## Five grants and only three of them are no-ops

    -f1   p13815  level 0, dealt       -> no-op
    -f2   p13816  level 0, dealt       -> no-op
    -f4   p13817  level 1, NOT dealt   -> real
    -f6   p13818  level 2, NOT dealt   -> real
    -f8   p13819  level 0, dealt       -> no-op

The knight established that the **level** and not the class decides this.
Here it decides it three times out of five on one chassis, which is why
each is measured rather than assumed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import _weapon_attack
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
from combat_engine.engine.events import PowerResolved, SurgeSpent
from combat_engine.engine.query import bloodied, has_combat_advantage, team

#: The one row the vice is chosen on. Three other parents read this ref
#: rather than carrying `chargen.BUILD_OPTIONS` entries of their own --
#: the module docstring has the argument.
VICE = "cf:paladin-blackguard-f3"

#: The two vices, in the order `BUILD_OPTIONS` lists them. Index 0 is the
#: one that trades hit points for damage; index 1 is the one that feeds on
#: combat advantage.
VICES = ("cf:paladin-blackguard-f3s0", "cf:paladin-blackguard-f3s1")

#: The row `-f11`'s extra effect and `-f20`'s teleport both answer.
CHANNEL = "p13816"


def _vice(c: Cast) -> int:
    """Which vice this blackguard took: 0 or 1.

    **One reader, and it asks about `VICE` whoever is calling.** `-f5`,
    `-f11` and `-f19` are parents of their own two-option families and
    none of them carries a `BUILD_OPTIONS` entry, precisely so that there
    is nothing for them to disagree with.

    Falls back to 0 for the same reason every parent in this wave falls
    back to its first option: a blackguard without a vice is a character
    missing the one feature its fork exists to choose, which is the harm
    `chargen.legs_for` is written to avoid.
    """
    chose = c.chosen_option(VICE) or VICES[0]
    return 1 if chose == VICES[1] else 0


def _a_weapon_attack(c: Cast) -> Any:
    """"A weapon attack" -- the keyword on the row that is rolling."""
    me, world = c.me, c.world
    return lambda ctx: _weapon_attack(world, me, ctx) is not None


# -- the rows that play ------------------------------------------------------


@power(
    "cf:paladin-blackguard-f0",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vengeance(c: Cast) -> None:
    """"Whenever you make a weapon attack against an enemy granting combat
    advantage to you, that enemy takes extra damage equal to your Charisma
    modifier."

    **Whenever, not once a turn** -- so this is a standing `c.bonus` with a
    live gate and **not** `pay_extra`, which is the once-a-turn latch the
    rogue, the ranger and the executioner share. Reading the cards side by
    side is the only way to tell those two apart, and getting it wrong in
    either direction is invisible: a latch here would quietly pay once a
    turn, and a bonus there would quietly pay every swing.

    Both halves of the gate are live. Combat advantage is asked at the
    moment of the roll for `query`'s reason -- flanking ends the instant an
    ally steps away -- and the weapon keyword is read off the rolling row.

    `ctx["target"]` is who the swing is against, which is what makes the
    advantage question answerable from inside a modifier.
    """
    me, world = c.me, c.world
    weapon = _a_weapon_attack(c)

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not weapon(ctx):
            return False
        return has_combat_advantage(world, me, victim)

    c.bonus("damage", c.cha_mod, on=me, until=When.ENCOUNTER,
            kind="untyped", when=gate)


def _grant(ref: str, got: str, no_op: bool) -> Any:
    """One of the five "you gain <power>" rows.

    The one helper the global rule allows, for a run of rows that share a
    shape -- five here, and each call below names its own ref and says
    which kind it is.

    `no_op` is **documentation and not behaviour**: the body is the same
    `c.grant_row` either way, because `grant_row` returning `None` for a
    row already held is exactly the right thing. What it records is the
    measurement, which the knight established is about the **level** and
    not the class: all five of these are `cls="paladin"` and only three
    are level 0.
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

    row.__name__ = "blackguard_grant_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'"You gain the `{got}` power."\n\n'
        + ("A no-op grant: a level-0 paladin row, so `chargen.loadout` has "
           "already dealt it and `c.grant_row` returns `None`. `#1259`."
           if no_op else
           "**A real grant.** It is `cls=\"paladin\"` like the no-op ones "
           "beside it and `loadout` does not deal it, because `loadout` "
           "deals level-0 rows and this is not one. The knight's `-f11` is "
           "the same lesson on another chassis.")
    )
    return row


blackguard_grant_1 = _grant("cf:paladin-blackguard-f1", "p13815", True)
blackguard_grant_2 = _grant("cf:paladin-blackguard-f2", CHANNEL, True)
blackguard_grant_4 = _grant("cf:paladin-blackguard-f4", "p13817", False)
blackguard_grant_6 = _grant("cf:paladin-blackguard-f6", "p13818", False)
blackguard_grant_8 = _grant("cf:paladin-blackguard-f8", "p13819", True)


@power(
    VICE,
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vice(c: Cast) -> None:
    """*"You gain a benefit associated with your vice."*

    **The one parent that carries the choice.** `-f5`, `-f11` and `-f19`
    print the same *"associated with your vice"* and read this row's answer
    instead of drawing their own -- the module docstring has the argument
    and `drivers.blackguard_vice` asserts the four never disagree.
    """
    c.grant_row(VICES[_vice(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:paladin-blackguard-f3s0",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    todo=("actions.offer_trait(requires=temp_hp)",),
)
def blackguard_vice_hunger(c: Cast) -> None:
    """One vice: hurt yourself before an attack roll to hit harder.

    *"Once per round while you have temporary hit points, you can take a
    free action to deal damage to yourself right before making an attack
    roll."*

    Nothing is written, and the gap is the **offer** rather than any of the
    effects. All three pieces exist -- `c.flat` for the self-damage,
    `c.bonus("damage", ...)` for the rider, `c.latch(per_turn=)` for the
    once-a-round -- but the clause is a free action a player **chooses** at
    a specific moment, *"right before making an attack roll"*, and a trait
    cannot put itself on the action menu. `cf:barbarian-berserker-f0` waits
    on the same facility under the same symbol shape, with a different
    requirement.

    Not `dropped=`: there is no second clause here that plays.
    """


@power(
    "cf:paladin-blackguard-f3s1",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vice_cruelty(c: Cast) -> None:
    """The other vice: +2 damage against an enemy granting you combat
    advantage, +4 while bloodied or beside somebody bloodied.

    Two gates and the second decides the **amount**, so one `c.bonus`
    cannot say it: the modifier is laid twice with complementary gates --
    +2 when the escalation does not hold and +4 when it does -- rather than
    +2 plus a conditional +2. Written that way because the card prints
    *"the bonus increases to +4"*, which is a replacement and not a second
    bonus, and two stacking modifiers would pay +6.

    *"Adjacent to a bloodied creature"* is **any** creature, not any
    enemy: the card says creature and a blackguard beside a bloodied ally
    qualifies. `query.bloodied` is the reader and `c.adjacent` the
    geometry, both asked live because both change inside a round.
    """
    me, world = c.me, c.world
    weapon = _a_weapon_attack(c)

    def against_a_giveaway(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not weapon(ctx):
            return False
        return has_combat_advantage(world, me, victim)

    def escalated() -> bool:
        if bloodied(world, me):
            return True
        # `c.allies() + c.enemies()` and not a `c.everyone()`, which does
        # not exist: the card says *creature*, so both sides count and a
        # blackguard beside a bloodied ally qualifies.
        return any(bloodied(world, who) and c.adjacent(who)
                   for who in (*c.allies(), *c.enemies()) if who != me)

    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: against_a_giveaway(ctx) and not escalated())
    c.bonus("damage", 4, on=me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: against_a_giveaway(ctx) and escalated())


@power(
    "cf:paladin-blackguard-f5",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vice_attack(c: Cast) -> None:
    """*"You gain an at-will attack power associated with your vice."*

    A parent with no choice of its own: it reads `VICE`'s answer. Both
    options are declared below and each is a **real** grant -- `p13837` and
    `p13843` are level-1 paladin rows, so `loadout` deals neither.
    """
    which = ("cf:paladin-blackguard-f5s0", "cf:paladin-blackguard-f5s1")
    c.grant_row(which[_vice(c)], on=c.me, until=When.ENCOUNTER)


blackguard_grant_5s0 = _grant(
    "cf:paladin-blackguard-f5s0", "p13837", False)
blackguard_grant_5s1 = _grant(
    "cf:paladin-blackguard-f5s1", "p13843", False)


@power(
    "cf:paladin-blackguard-f11",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vice_channel(c: Cast) -> None:
    """*"Your p13816 power gains an additional effect associated with your
    vice."*

    A parent reading `VICE`'s answer, like `-f5`. Both options are declared
    below and both watch `p13816` resolving.
    """
    which = ("cf:paladin-blackguard-f11s0", "cf:paladin-blackguard-f11s1")
    c.grant_row(which[_vice(c)], on=c.me, until=When.ENCOUNTER)


def _channel_rider(ref: str, what: str) -> Any:
    """One of `-f11`'s two extra effects on `p13816`.

    Both are *"2 + your Charisma modifier, 5 + at 23rd level"*, and the
    23rd-level step is written rather than marked: it is a **scaling
    number inside one clause**, which the card prints in the same sentence,
    not a separate feature row superseding a lower one. `#1261`'s line is
    about the second kind.
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
        amount = (5 if c.level >= 23 else 2) + c.cha_mod

        def rider(ev: PowerResolved) -> None:
            if getattr(ev, "actor", None) != me:
                return
            if getattr(ev, "power", "") != CHANNEL:
                return
            if ref.endswith("s0"):
                c.temp_hp(amount, on=me)
            else:
                c.bonus("damage", amount, on=me, until=When.EONT,
                        kind="untyped", once=True)

        c.watch(PowerResolved, rider, until=When.ENCOUNTER, on=me,
                label=c.ref)

    row.__name__ = "blackguard_channel_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One vice's extra effect on `{CHANNEL}`: {what}.\n\n"
        "`PowerResolved` and not a declared trigger, because the row is a "
        "standing fact about what `p13816` now does rather than something "
        "the blackguard answers. `once=True` on the damage half is *\"your "
        "next damage roll\"* -- the modifier is spent by the first roll "
        "that reads it, which is what that keyword is for."
    )
    return row


blackguard_channel_0 = _channel_rider(
    "cf:paladin-blackguard-f11s0", "temporary hit points")
blackguard_channel_1 = _channel_rider(
    "cf:paladin-blackguard-f11s1", "a bonus to the next damage roll")


@power(
    "cf:paladin-blackguard-f17",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_leech(c: Cast) -> None:
    """"When an ally spends a healing surge while adjacent to you, you gain
    temporary hit points equal to your Charisma modifier."

    `SurgeSpent` carries `actor`, and the geometry is read **when the surge
    is spent** rather than when the trait arms -- which is
    `cf:druid-protector-f0s0`'s reasoning for the same event: a party moves
    inside a fight and measuring adjacency at the top of it would answer
    about the wrong round.

    *"An ally"* excludes the blackguard itself, which is the edition's
    sense of the word and the same reading the protector's row takes.
    """
    me, world = c.me, c.world
    amount = c.cha_mod
    if amount <= 0:
        return

    def leech(ev: SurgeSpent) -> None:
        who = getattr(ev, "actor", None)
        if who is None or who == me:
            return
        if team(world, who) is not team(world, me):
            return
        if not c.adjacent(who):
            return
        c.temp_hp(amount, on=me)

    c.watch(SurgeSpent, leech, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:paladin-blackguard-f20",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_step(c: Cast) -> None:
    """"After you use p13816, you can take a free action to teleport up to 5
    squares."

    A `PowerResolved` watch, which is what *"after you use"* means -- and
    the same shape `cf:rogue-thief-f16` takes for the same sentence about a
    different row.

    *"Up to 5 squares"* and *"can"* are both offers, so `c.teleport` is
    handed the distance and going nowhere is one of the answers. A free
    action costs nothing the engine prices, so none is charged.

    **`who=` and not `on=`.** `c.teleport` spells the creature `who`, as
    `c.shift` does and `c.slide` does not -- getting it wrong is a
    `TypeError` at fire time rather than at import, which on
    `cf:rogue-thief-f16` was invisible until the row that triggers the
    watch was audited.
    """
    me = c.me

    def step(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if getattr(ev, "power", "") != CHANNEL:
            return
        c.teleport(5, who=me)

    c.watch(PowerResolved, step, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:paladin-blackguard-f22",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_inured(c: Cast) -> None:
    """"You gain resist 20 necrotic and resist 20 cold."

    Two calls, because `c.resist` takes one damage type and two types are
    two resistances -- the same reason AC and Reflex are two `c.bonus`
    calls elsewhere in this wave.

    Written although it is an epic-tier row, on the line
    `features/thief.py` draws: a resistance supersedes nothing, so what
    `#1261` costs here is a 1st-level blackguard having it early rather
    than the row being wrong.
    """
    for kind in (DamageType.NECROTIC, DamageType.COLD):
        c.resist(20, kind, until=When.ENCOUNTER, on=c.me)


# -- the two that add a use of the channel -----------------------------------


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p13815` per
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
        c.more_uses("p13815", 1, on=c.me)

    row.__name__ = "blackguard_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p13815` per encounter, still only once a turn.\n\n"
        "The same two gaps `cf:fighter-slayer-f3` and `cf:rogue-thief-f6` "
        "name, and the same two symbols -- the level is `#1261`'s, and "
        "nothing raises an existing row's per-encounter ceiling."
    )
    return row


blackguard_extra_use_7 = _extra_use("cf:paladin-blackguard-f7")
blackguard_extra_use_14 = _extra_use("cf:paladin-blackguard-f14")


# -- the six power picks, and the three that replace a daily -----------------


def _power_pick(ref: str, what: str, *, gained: bool = False) -> Any:
    """One of the six "you gain a new c4 attack or utility power" rows.

    `gained=True` for the four whose gain is now a
    `chargen.EXTRA_GAINS` entry. The card is a **gain** and not a pick
    from a named list, so no body can make it -- it is a slot in the hand
    the dealer builds. What was missing was the LEVEL the gain happens
    at, which `class_feature` carries none of; `combat_engine.levels`
    carries it now (`#1261`), so the entry is read rather than guessed.

    `out_of_combat=True` with it, because the whole row is a draw and has
    nothing to do on a board -- the same call `cf:warlock-binder-f6` and
    `cf:assassin-executioner-f6` already made.

    The other two are printed above the level this project imports, so
    their pool was never imported and an entry would deal nothing.
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
        todo=() if gained else ("chargen.power_choice()",),
        out_of_combat=gained,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "blackguard_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        + ("**Written as a `chargen.EXTRA_GAINS` entry**, keyed on this "
           "ref so `loadout` deals the extra power to a character holding "
           "this row and nobody else. An A/B against the entry deals "
           "exactly one more power, which is the check `#1112` exists for "
           "-- a wrong level deals nothing and says nothing."
           if gained else
           "`chargen.power_choice()`'s gap, and specifically the pool: "
           "this card is printed above the level this project imports, so "
           "there are no rows for the gain to draw from. `#1269`.")
    )
    return row


blackguard_pick_9 = _power_pick(
    "cf:paladin-blackguard-f9", "A `c4` attack power of your level or lower.",
    gained=True)
blackguard_pick_10 = _power_pick(
    "cf:paladin-blackguard-f10", "A `c4` utility power of your level or lower.",
    gained=True)
blackguard_pick_12 = _power_pick(
    "cf:paladin-blackguard-f12", "Another `c4` attack power.",
    gained=True)
blackguard_pick_13 = _power_pick(
    "cf:paladin-blackguard-f13", "Another `c4` utility power.",
    gained=True)
blackguard_pick_15 = _power_pick(
    "cf:paladin-blackguard-f15", "Another `c4` attack power.")
blackguard_pick_16 = _power_pick(
    "cf:paladin-blackguard-f16", "Another `c4` utility power.")


def _power_swap(ref: str, what: str) -> Any:
    """One of the three rows whose new power **replaces** a daily.

    A different symbol from `_power_pick`'s, and the distinction is the
    point: those add a power, these **trade** one -- *"this new power must
    replace one of the daily attack powers you already have"*. A draw that
    added without replacing would leave a blackguard a daily up on print,
    which is the wrong direction to land half of, so the swap is the gap
    and not the draw.
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
        todo=("chargen.power_swap(daily)",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "blackguard_swap_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        "The helper above has the argument for why this is its own symbol "
        "and not `chargen.power_choice()`. `cf:wizard-witch-f3`'s "
        "`turns.extended_rest(swap=)` is a different thing again -- that "
        "one swaps a *prepared* power at a rest, where this is a "
        "permanent trade at a level."
    )
    return row


blackguard_swap_18 = _power_swap(
    "cf:paladin-blackguard-f18",
    "A `c4` attack power replacing one of your dailies.")
blackguard_swap_21 = _power_swap(
    "cf:paladin-blackguard-f21",
    "Another `c4` attack power replacing one of your dailies.")
blackguard_swap_23 = _power_swap(
    "cf:paladin-blackguard-f23",
    "A named daily replacing one of your dailies -- and the spec gives its "
    "printed name rather than a ref, so even with the swap there would be "
    "nothing to grant.")


# -- the vice utility, whose two options the import did not resolve ----------


@power(
    "cf:paladin-blackguard-f19",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def blackguard_vice_utility(c: Cast) -> None:
    """*"You gain a utility power associated with your vice."*

    The fourth parent reading `VICE`'s answer. Both options are declared
    below and **both are `defect=`** -- so this row grants a row that
    refuses itself, which is correct and worth saying: the parent is not
    broken, its options are, and `usable` is what stops either reaching
    play.
    """
    which = ("cf:paladin-blackguard-f19s0", "cf:paladin-blackguard-f19s1")
    c.grant_row(which[_vice(c)], on=c.me, until=When.ENCOUNTER)


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

    row.__name__ = "blackguard_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


blackguard_defect_19s0 = _defective(
    "cf:paladin-blackguard-f19s0",
    "the spec names the granted power by its printed name instead of a "
    "ref, so the importer did not resolve it -- the same shape as "
    "cf:fighter-slayer-f13",
)
blackguard_defect_19s1 = _defective(
    "cf:paladin-blackguard-f19s1",
    "the spec names a power as an adjective plus the ref x_m3272a6, which "
    "is a theme row and not a paladin utility, and no ref for the power "
    "itself was resolved",
)
