"""The sentinel, the druid's third chassis and the largest in `#642`'s wave
so far.

47 printed rows, and a **season** chosen once on `-f0` and read by five
parents -- `-f0`, `-f1`, `-f9`, `-f10` and `-f12`. One
`chargen.BUILD_OPTIONS` entry with three options and four readers of it,
which is `features/blackguard.py`'s arrangement with one more option and
one more reader. That file has the argument; this one keeps the shape so
`drivers.sentinel_season` can assert the same property.

The shape:

    17  play
     2  another use of `p13506` per encounter
     3  an animal companion the engine cannot spawn
     6  rows a fight has no use for -- `out_of_combat=True`
     1  "two of the following abilities" -- a fork that deals TWO
    13  `defect=`: "one of the following powers" and no list
     5  of those 13 also replace a daily

## The companion is the one real gap and it is narrow

`-f1`'s three options each grant an **associate** -- `x10_1`, `x10_5`,
`x10_64` -- and the engine cannot put one on the board from a chosen
option. Measured rather than assumed: `c.call_companion("x10_1")` raises
`KeyError: no monster x10_1`, because that verb reads the **monster**
table and all three live in `associate` (88 rows).

`c.call_beast` is the near miss and shows exactly what is missing: it
spawns the ranger's beast by reading `beast:<ref>` off the **build**, so
the facility exists for a companion chosen with a leg and not for one
chosen with a `BUILD_OPTIONS` answer. One symbol, naming that.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.controllers_sd import out_of_heavy_armour
from combat_engine.content.features.strikers import _weapon_attack
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    REF,
    ActionType,
    Cast,
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import Dropped, SecondWind
from combat_engine.engine.query import team

#: The one row the season is chosen on. Four other parents read this ref.
SEASON = "cf:druid-sentinel-f0"

#: The three seasons, in the order `BUILD_OPTIONS` lists them.
SEASONS = ("cf:druid-sentinel-f0s0", "cf:druid-sentinel-f0s1",
           "cf:druid-sentinel-f0s2")

#: The row `-f5` and `-f7` would add a use of.
CHANNEL = "p13506"

#: The arms the first season's attack bonus names, as `Weapon.group`
#: spells them. The scimitar and the sickle are heavy and light blades
#: here; the spear and the dagger are their own groups.
_FIRST_ARMS = ("heavy blade", "light blade", "spear")


def _season(c: Cast) -> int:
    """Which season this sentinel took: 0, 1 or 2.

    One reader, asking about `SEASON` whoever is calling -- the
    arrangement `features/blackguard.py::_vice` records. Four independent
    draws would make a character a different season in each of its five
    features and nothing would notice.
    """
    chose = c.chosen_option(SEASON) or SEASONS[0]
    return SEASONS.index(chose) if chose in SEASONS else 0


def _wielding(c: Cast, *groups: str) -> bool:
    """Is the weapon in hand one of these groups?"""
    gear = c.world.get(c.me, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.group in groups


# -- the season, and its three benefits --------------------------------------


@power(
    SEASON,
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_season(c: Cast) -> None:
    """*"Each sentinel chooses a season ... your choice of season determines
    some of your class features."*

    **The one parent that carries the choice**, and the card says so
    outright -- which is rarer than it sounds: the blackguard's and the
    cavalier's equivalents leave the reader to notice that four rows share
    one decision. `-f1`, `-f9`, `-f10` and `-f12` read this row's answer.
    """
    c.grant_row(SEASONS[_season(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-sentinel-f0s0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    narrative=("skill:heal",),
)
def sentinel_season_first(c: Cast) -> None:
    """The first season: a weapon proficiency, an attack bonus with four
    arms, and a Heal bonus.

    **The proficiency clause is already true and so is not written.**
    `c.weapon_proficiency(bonus, group=)` *sets* a weapon's proficiency
    figure and its docstring is explicit that the figure *"is already
    added to every swing the weapon makes"* -- so the engine applies a
    scimitar's printed bonus to anybody holding one and models no
    unproficient penalty for it to lift. Writing the verb here would pay
    the bonus a second time, which is the failure its docstring calls
    *"too generous rather than inert, the kind nothing notices"*.

    The +1 is gated on the **group in hand** rather than installed flat,
    because the card names four weapons. Two of them are the heavy and
    light blade groups and the spear is its own; the sickle is a light
    blade too, so three group names cover all four printed arms. Said
    out loud because it looks like a shortfall and is not.

    Untyped: a class feature stacks with everything.

    `narrative=("skill:heal",)` is the +2 to Heal checks, which is the
    one clause of the three with no combat meaning -- a Heal check is the
    story engine's, and `c.bonus("skill:heal", ...)` would be laid where
    nothing in a fight reads it. The other two clauses play, which is what
    makes `narrative=` right here and `out_of_combat=True` wrong.
    """
    me = c.me
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: _wielding(c, *_FIRST_ARMS))


@power(
    "cf:druid-sentinel-f0s1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    narrative=("skill:athletics",),
)
def sentinel_season_second(c: Cast) -> None:
    """The second season: a bigger die in a mace or a staff, and an
    Athletics bonus.

    *"When wielding a one-handed mace, you use a d10 for its weapon
    damage. When wielding a staff or a two-handed mace, you use a d12."*
    `c.weapon_dice` writes the die onto the creature's **own copy** of the
    weapon -- `chargen.spawn` makes a `replace(w)` per character -- so this
    needs no reader, which is the same argument `c.weapon_range` makes and
    `cf:ranger-hunter-f17` records.

    **Two-handed decides which die, so the hands are read and not the
    group.** A mace can be either, and the card gives it `d10` in one hand
    and `d12` in two; a staff is always the bigger one. Written as the
    hands first and the group second, because that is the order the
    sentence resolves in.

    The Athletics bonus is `narrative=`: the other clause plays.
    """
    gear = c.world.get(c.me, Gear)
    weapon = gear.main if gear is not None else None
    if weapon is None:
        return
    if weapon.group == "staff" or weapon.two_handed:
        if weapon.group in ("staff", "mace"):
            c.weapon_dice("1d12", ref=weapon.ref, on=c.me)
        return
    if weapon.group == "mace":
        c.weapon_dice("1d10", ref=weapon.ref, on=c.me)


@power(
    "cf:druid-sentinel-f0s2",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    narrative=("skill:endurance",),
)
def sentinel_season_third(c: Cast) -> None:
    """The third season: a shield bonus behind a spear or a staff, and an
    Endurance bonus.

    Two calls, because AC and Reflex are separate keys and one `c.bonus`
    pays only one of them. `kind="shield"` because the card prints the
    word, which matters: a sentinel that somehow also carries a shield
    gets one bonus and not two -- `cf:fighter-knight-f4` is the same
    sentence for a quarterstaff.

    The weapon is read once at arming, as every standing weapon gate in
    this tree is.

    The Endurance bonus is `narrative=`: the other clause plays.
    """
    if not _wielding(c, "spear", "staff"):
        return
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="shield")
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, kind="shield")


# -- the grants -------------------------------------------------------------


def _grant(ref: str, got: str, why: str) -> Any:
    """One of the six "you gain <power>" rows."""

    @power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "sentinel_grant_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f'"You gain the `{got}` power."\n\n{why}'
    return row


sentinel_grant_2 = _grant(
    "cf:druid-sentinel-f2", CHANNEL,
    "A no-op grant: a level-0 druid row, already dealt -- and the one "
    "`-f5` and `-f7` would add a use of. `#1259`.")
sentinel_grant_3 = _grant(
    "cf:druid-sentinel-f3", "p1455",
    "**A real grant, and the class is why.** `p1455` is "
    '`cls="cleric"`, so `loadout` deals it to a cleric and not to a '
    "druid -- the fourth chassis in this wave to grant another class's "
    "row, after the berserker, the scout and the cavalier.")
sentinel_grant_8 = _grant(
    "cf:druid-sentinel-f8", "p13524",
    "A no-op grant: a level-0 druid row, already dealt. `#1259`.")
sentinel_grant_10s0 = _grant(
    "cf:druid-sentinel-f10s0", "p13540",
    "A no-op grant: a level-0 druid row, already dealt. One of `-f10`'s "
    "three options.")
sentinel_grant_10s1 = _grant(
    "cf:druid-sentinel-f10s1", "p13541",
    "A no-op grant: a level-0 druid row, already dealt.")
sentinel_grant_10s2 = _grant(
    "cf:druid-sentinel-f10s2", "p16117",
    "A no-op grant: a level-0 druid row, already dealt.")


@power(
    "cf:druid-sentinel-f4",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_hardiness(c: Cast) -> None:
    """"While you are not wearing heavy armor, you can use your Constitution
    modifier in place of your Dexterity or Intelligence modifier to
    determine your AC."

    `cf:druid-f1`'s first branch and `cf:druid-protector-f0s0`'s first
    clause, word for word, on a third chassis of one class. Written out
    again for `cf:rogue-thief-f1`'s reason: a sentinel is dealt neither of
    the others.

    The reading is `cf:warden-f1`'s, which `guardians._ability_for_ac`
    records: light armour already takes the better of Dexterity and
    Intelligence, so the substitution is worth the **difference** and only
    when it is a gain -- which is what the printed "can" makes it.
    """
    if not out_of_heavy_armour(c):
        return
    gain = c.con_mod - max(c.dex_mod, c.int_mod)
    if gain > 0:
        c.bonus(AC, gain, until=When.ENCOUNTER, on=c.me, kind="untyped")


# -- the companion, which the engine cannot spawn ---------------------------


@power(
    "cf:druid-sentinel-f1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_companion(c: Cast) -> None:
    """*"You gain an animal companion associated with the season you chose."*

    A parent reading `SEASON`'s answer. All three options are declared
    below and all three are refused -- so this row grants a row that
    refuses itself, which is correct and the same case
    `cf:paladin-blackguard-f19` and `cf:paladin-cavalier-f14` are in:
    the parent is not broken, its options are.
    """
    which = ("cf:druid-sentinel-f1s0", "cf:druid-sentinel-f1s1",
             "cf:druid-sentinel-f1s2")
    c.grant_row(which[_season(c)], on=c.me, until=When.ENCOUNTER)


def _companion(ref: str, got: str) -> Any:
    """One of `-f1`'s three animal companions.

    **Written, and the symbol was naming the wrong layer.** It said the
    gap was a chargen writer -- *"the facility exists for a companion
    chosen with a leg and not for one chosen with a `BUILD_OPTIONS`
    answer"* -- and that was a reasonable reading of a true measurement:
    `c.call_companion("x10_1")` really did raise `KeyError: no monster
    x10_1`.

    But the row needs nothing from chargen. **This row IS the answer**:
    the parent chooses among the three and grants the one it drew, so by
    the time this body runs the character has already chosen it and the
    companion's ref is right here. What was missing was one branch in
    `c.call_companion`, which read the `monster` table and had no
    `associate` arm -- where `c.summon` has had one since `#459`. Added,
    and all three now field at the owner's bloodied value.

    `kind="beast"` because that is what the page calls them and what
    `c.call_beast` produces, so a row asking about the character's beast
    finds this one.
    """

    @power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
    )
    def row(c: Cast) -> None:
        c.call_companion(got, kind="beast")

    row.__name__ = "sentinel_companion_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One season's animal companion: `{got}`.\n\n"
        "The helper above has the measurement and the argument for the "
        "symbol."
    )
    return row


sentinel_companion_0 = _companion("cf:druid-sentinel-f1s0", "x10_1")
sentinel_companion_1 = _companion("cf:druid-sentinel-f1s1", "x10_5")
sentinel_companion_2 = _companion("cf:druid-sentinel-f1s2", "x10_64")


# -- the season's second benefit --------------------------------------------


@power(
    "cf:druid-sentinel-f9",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_season_gift(c: Cast) -> None:
    """*"Gain a benefit related to your druid's chosen season."*

    A parent reading `SEASON`'s answer, like `-f1`.
    """
    which = ("cf:druid-sentinel-f9s0", "cf:druid-sentinel-f9s1",
             "cf:druid-sentinel-f9s2")
    c.grant_row(which[_season(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-sentinel-f9s0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    dropped=("chargen.companion_from_option()",),
)
def sentinel_gift_first(c: Cast) -> None:
    """The first season's gift: dropping a non-minion heals both of you.

    *"When you or your `cf:druid-sentinel-f1` reduces a nonminion enemy to
    0 hit points, you and your `cf:druid-sentinel-f1` each regain 10 hit
    points."*

    **The sentinel's half plays and the companion's does not**, which is
    why this is `dropped=` rather than `todo=`: `Dropped` carries `actor`
    and `source`, so "you reduced it" is answerable, and `c.heal` pays the
    10. What cannot be written is the other two mentions of the companion
    -- it reducing the enemy, and it being healed -- because there is no
    companion on the board (`-f1s0`'s symbol, shared).

    *"Nonminion"* is `Health.max_hp > 1`, which is what a minion is in this
    engine. Asked of the creature that went down rather than of its stat
    block, because a minion raised to real hit points by anything would
    not be one.
    """
    me, world = c.me, c.world

    def on_drop(ev: Dropped) -> None:
        if getattr(ev, "source", None) != me:
            return
        victim = getattr(ev, "actor", None)
        if victim is None or victim == me:
            return
        if team(world, victim) is team(world, me):
            return
        from combat_engine.engine.components import Health

        health = world.get(victim, Health)
        if health is None or health.max_hp <= 1:
            return
        c.heal(10, on=me)

    c.watch(Dropped, on_drop, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:druid-sentinel-f9s1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_gift_second(c: Cast) -> None:
    """The second season's gift: *"your reach increases by 1 for melee
    weapon attacks."*

    **`c.reach` is the READER and not the writer**, which is worth saying
    because the name goes the other way: it answers *"how far this
    creature's melee attacks carry"* and takes a ref, not a number. The
    increase is `c.bonus("reach", 1, ...)` with a melee gate, which is
    what `powers/fighter/level_2_t3.py` and two other rows lay.

    The gate is the printed *"for melee weapon attacks"*. Both halves are
    asked -- the range kind off the context and the weapon keyword off the
    rolling row -- because a reach bonus read by a ranged line would be
    wrong and `ctx["range_kind"]` is one context key over four
    vocabularies (`#639`).
    """
    me, world = c.me, c.world

    def melee_weapon(ctx: dict[str, Any]) -> bool:
        if ctx.get("range_kind", "melee") != "melee":
            return False
        return _weapon_attack(world, me, ctx) is not None

    c.bonus("reach", 1, on=me, until=When.ENCOUNTER, when=melee_weapon)


@power(
    "cf:druid-sentinel-f9s2",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    dropped=("chargen.companion_from_option()",),
)
def sentinel_gift_third(c: Cast) -> None:
    """The third season's gift: becoming insubstantial on being bloodied.

    *"The first time each encounter that you or your living zephyr
    companion becomes bloodied, you can use an immediate reaction to
    become insubstantial and shift up to 5 squares. You are insubstantial
    until the start of your next turn."*

    The sentinel's half plays. `c.arm_trigger(Bloodied, ...,
    cost=IMMEDIATE_REACTION)` is the printed action -- a bare watch would
    hand the reaction out for free.

    *"The first time each encounter"* is `c.once_per_board`, **not** a
    `once=` on the trigger: `c.arm_trigger` takes no such keyword, and the
    verb that does store a once-a-board answer stores it on the `World`,
    which is what `content/CLAUDE.md` requires -- ten rows kept such a
    latch in a module dict keyed on `id(c.world)` and a collected board's
    address was reused.

    `When.SOTNT` is *"until the start of your next turn"*, clocked on the
    sentinel.

    Dropped: the companion becoming bloodied is the other trigger and
    there is no companion (`-f1s0`'s symbol, shared).
    """
    me = c.me

    def bloodied_me(ev: Any) -> bool:
        return getattr(ev, "actor", None) == me

    def vanish(ev: Any) -> None:
        if not c.once_per_board(me):
            return
        if not c.may("turn insubstantial and shift"):
            return
        c.insubstantial(on=me, until=When.SOTNT)
        c.shift(5, who=me)

    from combat_engine.engine.events import Bloodied

    c.arm_trigger(Bloodied, vanish, when=bloodied_me,
                  cost=ActionType.IMMEDIATE_REACTION,
                  until=When.ENCOUNTER, on=me, label=c.ref)


# -- the companion's power, and the second wind ------------------------------


@power(
    "cf:druid-sentinel-f10",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_companion_power(c: Cast) -> None:
    """*"You gain a power associated with your animal companion."*

    A parent reading `SEASON`'s answer. All three options are declared and
    all three are **no-op grants** -- level-0 druid rows the loadout has
    already dealt -- so this fork is about exclusivity in principle and
    about nothing in practice, which `#1259` is the issue for.
    """
    which = ("cf:druid-sentinel-f10s0", "cf:druid-sentinel-f10s1",
             "cf:druid-sentinel-f10s2")
    c.grant_row(which[_season(c)], on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-sentinel-f12",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_second_wind(c: Cast) -> None:
    """*"Whenever you use your second wind, choose one ally within 10 squares
    of you. That ally gains a benefit determined by the season."*

    A parent reading `SEASON`'s answer. The three options each carry the
    whole clause -- the trigger, the choosing and the benefit -- because
    the card repeats all of it on each, which is unusual and is why this
    parent grants rather than watching the event itself.
    """
    which = ("cf:druid-sentinel-f12s0", "cf:druid-sentinel-f12s1",
             "cf:druid-sentinel-f12s2")
    c.grant_row(which[_season(c)], on=c.me, until=When.ENCOUNTER)


def _chosen_ally(c: Cast, me: int) -> int | None:
    """*"Choose one ally within 10 squares of you."*

    The half all three of `-f12`'s gifts genuinely share. The **benefit**
    is not shared, and that is why the three rows below are hand-written
    rather than minted by one helper: `scripts/bonuses.py` reads each
    ref's own source for its `kind=`, so a single decorated body served
    all three refs the one `kind="power"` call in it -- and reported `s0`
    and `s1` as laying a power-typed bonus when `s0` lays concealment and
    `s1` lays resistance. Three bodies, one chooser, and the static read
    is right for each.

    `c.within(radius, of=, side=)` RETURNS the list -- it is not a
    predicate, which the name invites. Reading it as `c.within(ally, 10)`
    type-checks and answers about the wrong thing entirely.
    """
    near = [a for a in c.within(10, of=me, side="ally") if a != me]
    if not near:
        return None
    return c.choose(near, f"{c.ref}: which ally")


@power(
    "cf:druid-sentinel-f12s0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    dropped=("c.end_ongoing()",),
)
def sentinel_wind_0(c: Cast) -> None:
    """One season's second-wind gift: an ongoing damage effect ends and the
    ally gains partial concealment.

    Only the concealment is laid: `c.ongoing` LAYS ongoing damage and
    takes no `clear=`, and nothing in the tree ends one --
    `c.end_effect(carrying=)` narrows by `Condition` and ongoing damage is
    not one. The marker names that half.

    No `kind=` because the card names no bonus at all -- concealment is
    not a +N of any type.
    """
    me = c.me

    def gift(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) != me:
            return
        friend = _chosen_ally(c, me)
        if friend is not None:
            c.conceal(on=friend, until=When.EONT)

    c.watch(SecondWind, gift, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:druid-sentinel-f12s1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_wind_1(c: Cast) -> None:
    """One season's second-wind gift: *"the chosen ally gains resist 10 to
    all damage until the end of your next turn."*

    `c.resist` with no damage type, which is *all damage*. No `kind=`
    because resistance is not a bonus and the card gives it no type.
    """
    me = c.me

    def gift(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) != me:
            return
        friend = _chosen_ally(c, me)
        if friend is not None:
            c.resist(10, until=When.EONT, on=friend)

    c.watch(SecondWind, gift, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:druid-sentinel-f12s2",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_wind_2(c: Cast) -> None:
    """One season's second-wind gift: *"the chosen ally gains a +5 power
    bonus to damage rolls until the end of your next turn."*

    `kind="power"` because this card is the one of the three that prints
    the word, so two sentinels' gifts do not stack. Checked against the
    page rather than copied from its siblings -- the other two print no
    bonus type because they lay no bonus.
    """
    me = c.me

    def gift(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) != me:
            return
        friend = _chosen_ally(c, me)
        if friend is not None:
            c.bonus("damage", 5, on=friend, until=When.EONT, kind="power")

    c.watch(SecondWind, gift, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the two extra uses -----------------------------------------------------


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p13506` per
    encounter."""

    @power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
    )
    def row(c: Cast) -> None:
        c.more_uses("p13506", 1, on=c.me)

    row.__name__ = "sentinel_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p13506` per encounter, still only once a turn.\n\n"
        "**Both halves landed.** `c.more_uses` raises an existing row's "
        "per-encounter allowance, read at the one site in `dsl.usable` "
        "that compares spent against allowed; and `combat_engine.levels` "
        "carries the printed level, so `chargen.ladder_row` deals this "
        "rung when the page says rather than at 1. `#1261`.\n\n"
        "The *\"only once per turn\"* half needs nothing: the raised row "
        "is a triggered no-action row, and `once_per_round` is tested "
        "separately from the allowance so this does not touch it."
    )
    return row


sentinel_extra_use_5 = _extra_use("cf:druid-sentinel-f5")
sentinel_extra_use_7 = _extra_use("cf:druid-sentinel-f7")


# -- the six rows a fight has no use for ------------------------------------


def _inert(ref: str, what: str, why: str) -> Any:
    """One of the six rows that are complete and inert in a fight.

    `out_of_combat=True` and not `narrative=`: these have no second
    clause, which is the distinction `cf:ranger-scout-f17s1` had to be
    corrected on -- the sweep reported four `narrative=` rows as newly
    silent rather than excusing them, because a narrative row is supposed
    to have a combat half to be silent beside.
    """

    def row(c: Cast) -> None:
        pass

    row.__name__ = "sentinel_inert_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = (
        f"{why}\n\n"
        f"`out_of_combat=True`: a {what} clause whose whole effect happens "
        "outside a fight. Empty rather than a `c.note` -- a trait runs at "
        "the start of every fight and a line in the log would announce "
        "something that is not happening."
    )
    return power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
        out_of_combat=True,
    )(row)


sentinel_inert_6 = _inert(
    "cf:druid-sentinel-f6", "short-rest",
    "Three questions put to beasts and plants, once a day on a short rest.")
sentinel_inert_11 = _inert(
    "cf:druid-sentinel-f11", "disease and ageing",
    "No longer ageing, and immune to diseases of the sentinel's level or "
    "lower -- neither of which a `World` has a field for.")
sentinel_inert_13s0 = _inert(
    "cf:druid-sentinel-f13s0", "diplomacy",
    "A bonus to social checks against beasts, and simple commands they "
    "are under no compulsion to obey.")
sentinel_inert_13s1 = _inert(
    "cf:druid-sentinel-f13s1", "short-rest",
    "The party adds 2 to a healing surge taken on a short rest in a "
    "sheltered place.")
sentinel_inert_13s2 = _inert(
    "cf:druid-sentinel-f13s2", "athletics",
    "A climb the sentinel succeeds at becomes easier for the allies who "
    "watched it.")
sentinel_inert_13s3 = _inert(
    "cf:druid-sentinel-f13s3", "perception",
    "The party sleeps through an extended rest without the usual penalty.")
sentinel_inert_13s4 = _inert(
    "cf:druid-sentinel-f13s4", "perception",
    "A short-rest sweep of the surrounding area.")


@power(
    "cf:druid-sentinel-f13",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def sentinel_abilities(c: Cast) -> None:
    """*"You gain **two** of the following abilities of your choice."*

    `cf:ranger-scout-f17`'s and `cf:ranger-hunter-f20`'s gap -- a fork
    that deals **two** where `chargen.BUILD_OPTIONS` deals one. Five
    options are declared below, so the content is here and what is
    missing is the arity.

    Three chassis now wait on this, which is what makes it worth a symbol
    of its own rather than folding into `chargen.power_choice()`: that one
    is a draw from a *family*, and this is a pick of N from a *printed
    list the table already holds*.

    **Written: `chargen.OPTION_PICKS` carries the arity.** The fork
    now deals TWO distinct options and `c.chosen_options` reads both,
    so this grants exactly what the card prints -- not one, which is
    half the feature, and not all five, which is stronger than print.
    `rng.sample` is what makes them distinct, which a second
    `BUILD_OPTIONS` entry could not have guaranteed.
    """
    for took in c.chosen_options("cf:druid-sentinel-f13") or [
            "cf:druid-sentinel-f13s0", "cf:druid-sentinel-f13s1"]:
        c.grant_row(took, on=c.me, until=When.ENCOUNTER)



def _printed_pick(ref: str, options: tuple[str, ...], what: str) -> Any:
    """A row printing *"one of the following powers"* with the list recovered.

    These carried `defect=` saying the spec *"lists nothing, so there is no
    set to choose from"*. The **spec** lists nothing; the compendium's class
    page prints the list immediately after the sentence, and every power in
    it is already imported. So the marker was describing the import rather
    than the source. `#1268`.

    How each list was recovered, and why it is a join rather than a parse:
    the page carries a `LEVEL N <CHASSIS> <USAGE> POWER` banner above the
    sentence, so a section is bounded on both sides; within it, the options
    are found by asking which of **this class's already-imported power
    names at that level** appear in the section. Presence of a known name,
    never a guess at where an unknown one ends -- so a boundary read wrongly
    cannot invent a power. The join is on `(level, usage)` from the banner
    against `combat_engine.levels` on this ref, and it **refuses** rather
    than guessing wherever the number of features at a level does not match
    the number of printed sections: the sentinel prints two level-1 banners
    (at-will and daily) and an earlier pass gave both features the first
    list.

    `chargen.BUILD_OPTIONS` carries the options and `c.chosen_option` reads
    the draw, which is the arrangement the pact forks already use -- and
    `c.grant_row` grants a power ref as readily as a feature one.
    """

    @power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
    )
    def row(c: Cast) -> None:
        c.grant_row(c.chosen_option(ref) or options[0], on=c.me,
                    until=When.ENCOUNTER)

    row.__name__ = "sentinel_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain one of the following powers of your choice."* {what}\n\n'
        f"{len(options)} options, recovered from the printed page rather "
        f"than from the spec -- see `_printed_pick`. `#1268`."
    )
    return row


def _defective(ref: str, swaps: bool) -> Any:
    """One of the thirteen "one of the following powers" rows with no
    list."""

    why = ("the spec reads 'you gain one of the following powers of your "
           "choice' and then lists nothing, so there is no set to choose "
           "from")
    if swaps:
        why += (", and the new power is also meant to replace a daily the "
                "character already has")

    @power(
        ref,
        level=0,
        cls="druid",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.PRIMAL],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "sentinel_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


# **The in-scope ones had their list recovered from the page.**
# `#1268`: the spec lists nothing, the class page prints the list
# straight after the sentence, and every power in it is already
# imported. The rest are printed above level 10, which this
# project does not import, so they keep the marker.
sentinel_pick_14 = _printed_pick(
    "cf:druid-sentinel-f14",
    ('p13507', 'p13508', 'p13509'),
    "The level-1 at-will list.")
sentinel_pick_15 = _printed_pick(
    "cf:druid-sentinel-f15",
    ('p13510', 'p13511', 'p13512'),
    "The level-1 daily list.")
sentinel_pick_16 = _printed_pick(
    "cf:druid-sentinel-f16",
    ('p13513', 'p13514', 'p13515', 'p13516'),
    "The level-2 utility list.")
sentinel_pick_17 = _printed_pick(
    "cf:druid-sentinel-f17",
    ('p13517', 'p13518', 'p13519'),
    "The level-5 daily list.")
sentinel_pick_18 = _printed_pick(
    "cf:druid-sentinel-f18",
    ('p13520', 'p13521', 'p13522', 'p7393'),
    "The level-6 utility list.")
sentinel_pick_19 = _printed_pick(
    "cf:druid-sentinel-f19",
    ('p13525', 'p13526', 'p13527'),
    "The level-9 daily list.")
sentinel_pick_20 = _printed_pick(
    "cf:druid-sentinel-f20",
    ('p13528', 'p13529', 'p9667'),
    "The level-10 utility list.")
for _n in (22, 24):
    globals()[f"sentinel_defect_{_n}"] = _defective(
        f"cf:druid-sentinel-f{_n}", False)
for _n in (21, 23, 25, 26):
    globals()[f"sentinel_defect_{_n}"] = _defective(
        f"cf:druid-sentinel-f{_n}", True)
