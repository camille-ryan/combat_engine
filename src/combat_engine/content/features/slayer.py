"""The slayer, the fighter's second chassis.

`#642`'s wave. 26 printed rows, and the first chassis in the wave where
**more than half of what plays needed no new verb** -- `c.draws_free`,
`c.immune`, `c.resist(when=)` and `c.save(when_="start")` were each written
for something else and each is the whole of a clause here.

The shape:

    12 rows   play
     5 rows   a ladder rung that supersedes a lower number -- `#1261`
     2 rows   another use of `p12668` per encounter
     2 rows   one more fighter stance, chosen at creation
     6 rows   `defect=`: the import lost what the row names

The line on a ladder rung is `features/thief.py`'s and is not re-argued
here: a rung that **supersedes** a lower number is not written, because
every class feature arms at the start of every fight and `class_feature`
carries no level, so writing `-f16` pays a 1st-level slayer `8 + Dex`.
A rung that merely adds -- `-f7`'s +1 to saves -- is written.

## The six the import cannot supply, and one of them is a new kind

`-f10` names **itself** as the power it grants, and `-f18` through `-f22`
print *"one of the following powers of your choice"* and then no list. Both
are the thief's two shapes exactly.

`-f13` is new: its spec prints a power's **name** where every other grant
in the tree prints a ref, so the importer did not resolve it and there is
nothing to grant. Searched before concluding -- no fighter power in
`game.db` carries that word anywhere in its spec -- which is the check the
root `CLAUDE.md` asks for before calling a source absent. `defect=`, with
the reason saying it is the import and not the page.
"""

from __future__ import annotations

from typing import Any

from combat_engine.armour import ARMOUR_SPEED
from combat_engine.content.features.strikers import _weapon_attack
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Condition,
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import PowerResolved, TurnStart

#: The row every rider on this chassis answers.
STRIKE = "p12668"

#: "While wearing heavy armor" -- the three the armour table charges a
#: speed penalty for, which is the same list `strikers_sb.HEAVY` names from
#: the other side. Derived rather than written: `ARMOUR_SPEED` is the
#: printed table and `-f15` is about exactly the armours it penalises, so
#: a second hand-written list here could disagree with the one the
#: character's speed was computed from.
HEAVY = tuple(sorted(k for k, v in ARMOUR_SPEED.items() if v < 0))


def _in_heavy_armour(c: Cast) -> bool:
    """"While wearing heavy armor", off the live `Gear`."""
    gear = c.world.get(c.me, Gear)
    return gear is not None and gear.armour in HEAVY


def _a_weapon_attack(c: Cast) -> Any:
    """"Weapon attacks" -- the keyword on the row that is rolling, asked of
    the weapon the swing is using.

    `strikers._weapon_attack` rather than a keyword test alone, because it
    answers both halves at once: it returns `None` for a row without the
    weapon keyword and the weapon otherwise. The slayer's two standing
    bonuses have no weapon-group clause -- unlike the thief's -- so the
    weapon itself is not inspected, only its existence.
    """
    me, world = c.me, c.world
    return lambda ctx: _weapon_attack(world, me, ctx) is not None


def _an_opportunity_attack(ctx: dict[str, Any]) -> bool:
    """"Damage from opportunity attacks."

    `ctx["opportunity"]` is the word `cf:rogue-scoundrel-f1`'s Charisma
    tactic already reads for the same distinction, so this is the same
    question and not a new one.
    """
    return bool(ctx.get("opportunity"))


# -- the twelve rows that play -----------------------------------------------


@power(
    "cf:fighter-slayer-f0",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_power_strike(c: Cast) -> None:
    """"You gain a bonus to the damage rolls of weapon attacks. The bonus
    equals your Dexterity modifier."

    Untyped, because the card prints no type word. Gated on the row being
    a **weapon** attack, which is the only clause here -- the slayer's
    bonus names no weapon group, where the thief's four arms do, so this
    gate is strictly "is a weapon swinging".

    **The ladder three rows climb is written here**, which is the `#550`
    arrangement a class feature's turn: `-f5`, `-f9` and `-f16` each print
    *"the bonus ... increases to N + your Dexterity modifier"*, and no
    modifier can reach into another row's `c.bonus` call. So they are
    pointers carrying `implemented_in=` and this body reads which of them
    the character holds.

    **The highest held rung wins, and that is what "increases to" means.**
    A 15th-level slayer holds `-f5` and `-f9` both -- they are separate
    printed features and `chargen` deals every rung at or below the
    character's level -- so adding them would pay `2 + 5 + Dex` where the
    page says `5 + Dex`. `max` is the whole of the superseding rule.

    **Read off `Powers.known` rather than through `c.change_amount`**,
    deliberately. That verb is the general facility for raising a number
    another row hands out, and it loses a race here: all four of these arm
    as traits, `turns.arm_traits` walks them in its own order, and
    `c.bonus` fixes its amount when it is laid -- so a rung arming after
    this row would change a number that had already been paid. `c.feat`
    asks what the character *holds*, which `chargen` settled before any
    arming, so there is no order to get wrong.
    """
    # **Each rung named in this body's own source**, which is what
    # `lint.py` requires of an `implemented_in=` pointer (`#553`) and is
    # the right shape anyway: three hand-written lines, one per printed
    # rung, rather than a table a reader has to go and find.
    #
    # Plain `if` and not `elif`, in rising order, so the **highest held**
    # rung wins -- a 25th-level slayer holds all three and the page says
    # `8 + Dex`, not `2 + 5 + 8 + Dex`.
    step = 0
    if c.feat("cf:fighter-slayer-f5"):
        step = 2
    if c.feat("cf:fighter-slayer-f9"):
        step = 5
    if c.feat("cf:fighter-slayer-f16"):
        step = 8
    c.bonus("damage", step + c.dex_mod, on=c.me,
            until=When.ENCOUNTER, kind="untyped", when=_a_weapon_attack(c))


@power(
    "cf:fighter-slayer-f1",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_strike(c: Cast) -> None:
    """"You gain the p12668 power."

    A no-op grant: `p12668` is declared `cls="fighter"` at level 0, so
    `chargen.loadout` has already dealt it. Written out because `-f3`,
    `-f8` and all three of `-f21`'s options are about that row. `#1259`.
    """
    c.grant_row(STRIKE, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-slayer-f2",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_accuracy(c: Cast) -> None:
    """"You gain a +1 bonus to the attack rolls of weapon attacks."

    `-f0`'s gate and the other key. Untyped: a class feature stacks with
    everything and no type word is printed.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack(c))


@power(
    "cf:fighter-slayer-f4",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_handy(c: Cast) -> None:
    """"Once during each of your turns, you can take a free action to draw
    or stow a weapon and then draw another weapon."

    `c.draws_free` is the whole of it and was written for a racial trait
    printing the same sentence. What it changes is what a draw **costs** --
    the draw itself has been offered since a ranger who put a bow away
    could otherwise never pick it up -- and `per_turn=1` is the printed
    once-a-turn limit, refilled by `Gear.draws_left` at the start of each
    of this creature's turns.

    *"And then draw another weapon"* is the same allowance spent twice and
    needs nothing: a stow and a draw are both draws to `actions._wielding`,
    so one free action covering the pair is what `per_turn=1` on a free
    cost already means.
    """
    c.draws_free(cost=ActionType.FREE, per_turn=1, on=c.me,
                 until=When.ENCOUNTER)


@power(
    "cf:fighter-slayer-f7",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_resolve(c: Cast) -> None:
    """"You gain a +1 bonus to saving throws."

    Written although it is a ladder rung, on the module docstring's line:
    it supersedes nothing, so `#1261` costs it being early rather than
    being wrong.
    """
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="untyped")


@power(
    "cf:fighter-slayer-f12",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_unyielding(c: Cast) -> None:
    """"While wearing heavy armor, you have resistance to all damage from
    opportunity attacks. The resistance equals 10 + your Dexterity
    modifier."

    Two gates read at two different times, which is the arrangement
    `cf:barbarian-berserker-f2` records: the armour is read **once** when
    the trait arms, because nothing in a fight changes what is worn, and
    the opportunity test is read **live** in a `when=`, because it is a
    fact about the blow and not about the creature.

    *"Resistance to all damage"* is `dtype=None`, which is what `c.resist`
    means by an unqualified amount -- not a loop over the eleven types.
    """
    if not _in_heavy_armour(c):
        return
    c.resist(10 + c.dex_mod, until=When.ENCOUNTER, on=c.me,
             when=_an_opportunity_attack)


@power(
    "cf:fighter-slayer-f14",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_relentless(c: Cast) -> None:
    """"You are immune to the slowed condition."

    `c.immune` takes conditions and `until=When.ENCOUNTER` is the whole
    fight, which is what a standing immunity is. One condition and not a
    list: the card names one.
    """
    c.immune(Condition.SLOWED, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:fighter-slayer-f15",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_stride(c: Cast) -> None:
    """"You ignore penalties to speed for wearing heavy armor."

    **The penalty is already spent by the time this runs**, which is what
    makes the clause expressible at all: `chargen.spawn` computes
    `speed=speed + ARMOUR_SPEED.get(line.armour, 0)`, so a slayer in plate
    walks in a square slower and giving the square back *is* ignoring the
    penalty. Adding back exactly `-ARMOUR_SPEED[armour]` is therefore not
    an approximation of the sentence -- it is the same number, read from
    the same table.

    `combat_engine.armour` is the shared home for the printed armour
    numbers and is below every component (`#852`), so reading it here is
    the arrangement rather than a reach across a seam -- `features/
    racial.py` and `feats/general_o.py` already import this constant.

    Nothing is laid when the penalty is zero, which is every armour but
    the three heavy ones. Untyped: there is no printed bonus type on a
    sentence that removes a penalty.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return
    penalty = ARMOUR_SPEED.get(gear.armour, 0)
    if penalty >= 0:
        return
    c.bonus("speed", -penalty, on=c.me, until=When.ENCOUNTER, kind="untyped")


@power(
    "cf:fighter-slayer-f17",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_indomitable(c: Cast) -> None:
    """"At the start of your turn, you can make a saving throw against one
    effect that a save can end. If the saving throw succeeds, the effect
    ends, preventing it from affecting you on your current turn. If the
    saving throw fails, you still make a saving throw against the effect at
    the end of your turn."

    An extra save, taken early, that does not replace the ordinary one.
    `c.save(when_="start")` is the parameter that says so -- the engine
    rolls the usual end-of-turn saves regardless, so the printed second
    sentence needs nothing written for it.

    `bare=False`, so the slayer's own `-f7` bonus and anything else
    standing is read. The card prints no restriction on which effect, so
    `c.save` collects the ones a save can end and lets whoever is playing
    choose -- a headless run takes the oldest, which is `c.end_effect`'s
    rule for the same situation and for the same reason: it has had the
    most chances to lapse on its own.
    """
    me = c.me

    def early_save(ev: TurnStart) -> None:
        if getattr(ev, "actor", None) != me:
            return
        c.save(on=me, when_="start")

    c.watch(TurnStart, early_save, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:fighter-slayer-f21",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def slayer_mastery(c: Cast) -> None:
    """*"You gain one of the following benefits of your choice."*

    A **parent**, so `chargen.ladder_row` deals it and it chooses among its
    own three options. `chargen.BUILD_OPTIONS` and not a leg: the fighter's
    six legs are the weaponmaster's fork, a character takes one leg, and
    these three options are keyed to a weapon group rather than to a build.

    All three are declared below, so this grants rather than repeating what
    they say.
    """
    chose = (c.chosen_option("cf:fighter-slayer-f21")
             or "cf:fighter-slayer-f21s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


def _mastery(ref: str, groups: tuple[str, ...], what: str) -> Any:
    """One of `-f21`'s three benefits: a rider on `p12668` keyed to a
    weapon group.

    The one helper the global rule allows, for a run of rows that share a
    shape -- three here, each watching the same row and each gated on its
    own printed group. Every call below names its own groups and its own
    effect out loud.

    **`PowerResolved` and not `Hit`.** The benefit is *"when you use
    `p12668`"*, and `p12668` is itself a no-action row triggered by a melee
    basic attack landing -- so watching `Hit` would fire the rider on every
    basic hit whether or not the strike was spent. `PowerResolved` carries
    `trigger`, which is that `Hit`, so the triggering victim is reachable
    without a second guess.

    **`c.slide(on=)` and `c.shift(who=)` spell the creature differently**,
    and getting it wrong is a `TypeError` at fire time rather than at
    import -- which on `cf:rogue-thief-f16` was invisible until the row
    that *triggers* the watch was audited. Checked against the signature
    here instead.
    """
    hit_groups = frozenset(groups)

    @power(
        ref,
        level=0,
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        me = c.me

        def rider(ev: PowerResolved) -> None:
            if getattr(ev, "actor", None) != me:
                return
            if getattr(ev, "power", "") != STRIKE:
                return
            gear = c.world.get(me, Gear)
            weapon = gear.main if gear is not None else None
            if weapon is None or weapon.group not in hit_groups:
                return
            victim = getattr(getattr(ev, "trigger", None), "target", None)
            if ref.endswith("s0"):
                if victim is not None and c.may("knock it prone"):
                    c.prone(on=victim)
                return
            others = [foe for foe in c.enemies()
                      if foe != victim and c.adjacent(foe)]
            if ref.endswith("s1"):
                for foe in others:
                    c.flat(c.dex_mod, on=foe)
                return
            for foe in others:
                c.slide(1, on=foe)

        c.watch(PowerResolved, rider, until=When.ENCOUNTER, on=me,
                label=c.ref)

    row.__name__ = "slayer_mastery_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One benefit: with {' or '.join(sorted(groups))}, {what}.\n\n"
        "The group is read off the weapon in hand when the strike resolves "
        "rather than when the trait arms -- a slayer carries more than one "
        "weapon and `-f4` is a feature about swapping them mid-turn, so "
        "measuring at arming would answer about the wrong one."
    )
    return row


slayer_mastery_0 = _mastery(
    "cf:fighter-slayer-f21s0", ("axe",), "the target can be knocked prone")
slayer_mastery_1 = _mastery(
    "cf:fighter-slayer-f21s1", ("staff",),
    "every other adjacent enemy takes the slayer's Dexterity modifier")
slayer_mastery_2 = _mastery(
    "cf:fighter-slayer-f21s2", ("heavy blade",),
    "every adjacent enemy but the target is slid 1 square")


# -- the five rungs that supersede a lower number ----------------------------


def _damage_rung(ref: str, value: int) -> Any:
    """One rung of `-f0`'s damage ladder, refused for want of a level."""

    @power(
        ref,
        level=0,
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        implemented_in=("cf:fighter-slayer-f0",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "slayer_damage_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"`cf:fighter-slayer-f0`'s damage bonus rises to {value} + "
        "Dexterity.\n\n"
        "**Written into `-f0`**, which is where a clause raising another "
        "row's number has to go: no modifier can reach into that row's "
        "`c.bonus` call, so the three `c.feat` reads are in that body. So "
        "this is a pointer and carries `implemented_in=`, exactly as a "
        "feat naming one power does.\n\n"
        "What made it unwritable was the level, not a verb: every class "
        "feature armed at the start of every fight because "
        "`class_feature` carries none, so this constant reached a "
        "1st-level slayer. `combat_engine.levels` carries the printed "
        "levels now and `chargen.ladder_row` reads them. `#1261`."
    )
    return row


slayer_damage_5 = _damage_rung("cf:fighter-slayer-f5", 2)
slayer_damage_9 = _damage_rung("cf:fighter-slayer-f9", 5)
slayer_damage_16 = _damage_rung("cf:fighter-slayer-f16", 8)


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p12668` per encounter."""

    @power(
        ref,
        level=0,
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.more_uses("p12668", 1, on=c.me)

    row.__name__ = "slayer_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p12668` per encounter, still only once a turn.\n\n"
        "The same two gaps `cf:rogue-thief-f6` names and the same two "
        "symbols -- the level is `#1261`'s, and nothing raises an existing "
        "row's per-encounter ceiling (`c.restore_use` hands one back, "
        "`c.regain_power` refreshes one, neither adds a slot).\n\n"
        "The *\"only once per turn\"* half needs nothing: `p12668` is a "
        "triggered no-action row and the turn limit is already how it "
        "behaves."
    )
    return row


slayer_extra_use_3 = _extra_use("cf:fighter-slayer-f3")
slayer_extra_use_8 = _extra_use("cf:fighter-slayer-f8")


def _another_stance(ref: str) -> Any:
    """One of the two rows reading "you gain one additional fighter
    stance"."""

    @power(
        ref,
        level=0,
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        todo=("chargen.power_choice()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "slayer_another_stance_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "One more fighter stance, chosen at creation.\n\n"
        "A draw from a named printed family, which is the gap "
        "`chargen.power_choice()` names. The family exists -- `p12688` is "
        "a fighter stance and is written -- so this is the draw and "
        "nothing else, as `cf:rogue-thief-f7` is.\n\n"
        "No level symbol: an extra choice at creation is not wrong early "
        "the way a superseding number is."
    )
    return row


slayer_another_stance_6 = _another_stance("cf:fighter-slayer-f6")
slayer_another_stance_11 = _another_stance("cf:fighter-slayer-f11")


# -- the six rows the import cannot supply -----------------------------------


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
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        # **Every option the build took, not the first of them.** A
        # fork that deals one answers a single-entry tuple, so this is
        # the same behaviour there -- and `cf:ranger-hunter-f19` and its
        # scout twin deal TWO, with more rungs adding a third and a
        # fourth, so granting `[0]` alone would hand over one aspect and
        # silently drop the rest. `chargen.OPTION_PICKS` and
        # `chargen.EXTRA_PICKS` decide how many.
        for took in c.chosen_options(ref) or options[:1]:
            c.grant_row(took, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "slayer_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain one of the following powers of your choice."* {what}\n\n'
        f"{len(options)} options, recovered from the printed page rather "
        f"than from the spec -- see `_printed_pick`. `#1268`."
    )
    return row


def _defective(ref: str, why: str) -> Any:
    """One of the six rows whose printed text is missing what it names.

    `defect=` and not `todo=`/`dropped=`: no symbol will ever close these,
    because the gap is in the source as imported. `usable` refuses the row
    and `dsl.entry_of` returns a `cf:` ref unchanged, so each refuses
    **only itself** -- which `drivers.thief_chassis` asserts for the six of
    the same shape on that chassis.
    """

    @power(
        ref,
        level=0,
        cls="fighter",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "slayer_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


slayer_defect_10 = _defective(
    "cf:fighter-slayer-f10",
    "the spec reads 'you gain the cf:fighter-slayer-f10 power' -- the "
    "feature names itself as the power it grants, and no such ref exists",
)
slayer_defect_13 = _defective(
    "cf:fighter-slayer-f13",
    "the spec names the granted power by its printed name instead of a "
    "ref, so the importer did not resolve it; no fighter power in game.db "
    "carries that word anywhere in its spec, so there is nothing to grant",
)
slayer_defect_18 = _defective(
    "cf:fighter-slayer-f18",
    "the spec reads 'you gain two of the following powers of your choice' "
    "and then lists nothing, so there is no set to choose from")
slayer_pick_19 = _printed_pick(
    "cf:fighter-slayer-f19",
    ('p12671', 'p12693', 'p12695', 'p12696'),
    "The level-2 utility list.")
slayer_pick_20 = _printed_pick(
    "cf:fighter-slayer-f20",
    ('p12698', 'p12699', 'p12700', 'p12701'),
    "The level-6 utility list.")
slayer_pick_22 = _printed_pick(
    "cf:fighter-slayer-f22",
    ('p12702', 'p12703', 'p12704', 'p12705'),
    "The level-10 utility list.")
