"""The knight, the fighter's third chassis and the wave's largest so far.

`#642`'s wave. 29 printed rows, and the first chassis where **three grants
in a row are each load-bearing for a different reason**:

    -f0   p12661   a fighter row, already dealt      -- no-op
    -f1   p12660   a fighter row, already dealt      -- no-op
    -f3   f3148    a FEAT, never dealt               -- real
    -f11  p12677   a fighter row, NOT dealt          -- real

The last one is worth the line: `p12677` is `cls="fighter"` like the other
three and `loadout` does **not** deal it, because it is not a level-0 row.
So "is it a fighter power" is not the test for whether a grant matters --
measured per ref rather than reasoned about, which is what `#1259` is for.

The shape:

    14  play
     5  a rung superseding a lower number -- `#1261`
     2  another use of `p12668` per encounter
     2  one more fighter stance, chosen at creation
     6  `defect=`: the import lost what the row names

Two rows are the slayer's word for word -- `-f5` is `cf:fighter-slayer-f2`
and `-f21` is `cf:fighter-slayer-f17` -- and are written out again rather
than shared, for `cf:rogue-thief-f1`'s reason: a knight is dealt no slayer
row, so if these did not pay the clause nobody would.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import _weapon_attack
from combat_engine.content.powers.barbarian.aura import aura_ring
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
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import PowerResolved, SecondWind, TotalDefence
from combat_engine.engine.query import team

#: The row three of the knight's riders answer.
STRIKE = "p12668"

#: The weapon `-f4` lets stand in for a shield.
STAFF = "staff"

#: The four defences `-f17`'s aura pays. Named rather than looped over a
#: `Defense` enum, because the card says "all defenses" and the enum is
#: where the engine happens to keep them -- if a fifth is ever added the
#: card still says four.
DEFENCES = (AC, FORT, REF, WILL)


def _a_weapon_attack(c: Cast) -> Any:
    """"Weapon attacks" -- the keyword on the row that is rolling.

    `cf:fighter-slayer-f0`'s gate and the same reader, because the two
    chassis print the same two standing bonuses.
    """
    me, world = c.me, c.world
    return lambda ctx: _weapon_attack(world, me, ctx) is not None


def _group_in_hand(c: Cast, groups: tuple[str, ...]) -> bool:
    """Is the weapon being swung one of these groups?

    Read when the strike resolves rather than when the trait arms, which is
    `cf:fighter-slayer-f21`'s reasoning: a fighter carries more than one
    weapon and nothing stops it swapping mid-turn.
    """
    gear = c.world.get(c.me, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.group in groups


# -- the fourteen rows that play ---------------------------------------------


@power(
    "cf:fighter-knight-f0",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_opportunity(c: Cast) -> None:
    """"You gain the p12661 power." A no-op grant -- a level-0 fighter row,
    already dealt. `#1259`."""
    c.grant_row("p12661", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-knight-f1",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_aura(c: Cast) -> None:
    """"You gain the p12660 power."

    A no-op grant here and **load-bearing on the berserker**, which is the
    same ref and the difference worth knowing: `p12660` is declared
    `cls="fighter"`, so a knight has it from `loadout` and
    `cf:barbarian-berserker-f1` has to hand it over. `#1259`.
    """
    c.grant_row("p12660", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-knight-f2",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_strike(c: Cast) -> None:
    """"You gain the p12668 power." A no-op grant -- the same row
    `cf:fighter-slayer-f1` grants, and the one `-f9`'s three options
    answer. `#1259`."""
    c.grant_row(STRIKE, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-knight-f3",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_bonus_feat(c: Cast) -> None:
    """"You gain the f3148 feat."

    **A real grant**, unlike the three around it: `f3148` is a feat, and
    `loadout` deals powers rather than feats, so nothing else puts it in
    reach. `c.grant_row` grants a feat because a feat is an ordinary row in
    `Powers.known` -- which `cf:assassin-executioner-f5` establishes and
    `drivers.executioner_guild` asserts.

    No choice to make here, so no `BUILD_OPTIONS` entry: the card names one
    feat.
    """
    c.grant_row("f3148", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-knight-f4",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    dropped=("Gear.counts_as(shield)",),
)
def knight_staff_shield(c: Cast) -> None:
    """A quarterstaff counts as a shield, and pays a shield bonus.

    *"You gain a +1 shield bonus to AC and Reflex"* is written: two calls,
    because AC and Reflex are separate keys and one `c.bonus` pays only one
    of them -- the mistake `cf:barbarian-f0` records at the top of
    `strikers_sb.py`. `kind="shield"` because the card prints the word,
    which matters: a knight that somehow also carries a shield gets one
    bonus and not two.

    Dropped: *"you are considered to be wielding a shield for powers and
    effects that require you to wield one."* `Gear.counts_as` exists and is
    the right home -- it is how a creature says a thing in hand is also
    something else -- but nothing reads it for the **shield** question;
    every shield test in the tree asks `Gear.shield` directly. One symbol,
    naming the field rather than the clause, because what is missing is a
    reader and not a writer.

    The staff is read once when the trait arms, as every standing weapon
    gate in this tree is. `group` and not a property: a quarterstaff is the
    `staff` group, which is what `cf:fighter-slayer-f21s1` also keys on.
    """
    gear = c.world.get(c.me, Gear)
    weapon = gear.main if gear is not None else None
    if weapon is None or weapon.group != STAFF:
        return
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="shield")
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, kind="shield")


@power(
    "cf:fighter-knight-f5",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_accuracy(c: Cast) -> None:
    """"You gain a +1 bonus to the attack rolls of weapon attacks."

    `cf:fighter-slayer-f2`'s sentence word for word. Written out rather
    than shared for `cf:rogue-thief-f1`'s reason: a knight is dealt no
    slayer row.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack(c))


@power(
    "cf:fighter-knight-f7",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_readiness(c: Cast) -> None:
    """"You gain a +2 bonus to initiative."

    **`c.initiative`, not `c.bonus("initiative", ...)`** --
    `Initiative.bonus` is summed before the d20 and `Mods` is never
    consulted, so the modifier would be laid and no roll would read it.
    `cf:rogue-thief-f11` records the measurement and `#1262` is why the
    sweep calls such a row SILENT: `adjust_initiative` emits nothing.

    **`-f12` raises it to +4 and is written here**, which is where a
    clause raising another row's number goes: that rung is a pointer
    carrying `implemented_in=` and this body reads whether it is held.
    Plain `if`, so the higher printed number replaces rather than adds --
    a 9th-level knight gets +4, not +6.

    Read off `Powers.known` with `c.feat` rather than through
    `c.change_amount`: both rows arm as traits in `arm_traits`' own order,
    and `c.initiative` pays its number when it is called, so a rung
    arming afterwards would raise a figure already spent.
    """
    bonus = 2
    if c.feat("cf:fighter-knight-f12"):
        bonus = 4
    c.initiative(bonus, on=c.me)


@power(
    "cf:fighter-knight-f8",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_damage(c: Cast) -> None:
    """"You gain a +1 bonus to the damage rolls of weapon attacks."

    `cf:fighter-slayer-f0`'s gate with a flat number instead of Dexterity,
    and the same ladder arrangement: `-f14` and `-f20` print *"increases
    to +2"* and *"+3"*, so they are pointers and this body reads them.
    Rising order and plain `if`, so the highest held wins -- a 25th-level
    knight holds both and the page says +3.
    """
    bonus = 1
    if c.feat("cf:fighter-knight-f14"):
        bonus = 2
    if c.feat("cf:fighter-knight-f20"):
        bonus = 3
    c.bonus("damage", bonus, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack(c))


@power(
    "cf:fighter-knight-f9",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_benefit(c: Cast) -> None:
    """*"You gain one of the benefits of your choice."*

    A **parent** choosing among three riders on `p12668`, each keyed to a
    weapon group -- the same arrangement `cf:fighter-slayer-f21` has, on
    the same row, with different groups and different effects.
    `chargen.BUILD_OPTIONS` and not a leg: the fighter's six legs are the
    weaponmaster's.
    """
    chose = (c.chosen_option("cf:fighter-knight-f9")
             or "cf:fighter-knight-f9s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


def _benefit(ref: str, groups: tuple[str, ...], what: str) -> Any:
    """One of `-f9`'s three benefits: a rider on `p12668` keyed to a group.

    The one helper the global rule allows, for three rows that share a
    shape. Each call below names its own groups and its own effect.

    **`PowerResolved` and not `Hit`**, for `cf:fighter-slayer-f21`'s
    reason: the benefit is *"when you use `p12668`"*, and `p12668` is
    itself a no-action row triggered by a melee basic attack landing -- so
    watching `Hit` would fire on every basic hit whether or not the strike
    was spent. `PowerResolved.trigger` is that `Hit`, which is where the
    victim comes from.
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
            if not _group_in_hand(c, tuple(hit_groups)):
                return
            victim = getattr(getattr(ev, "trigger", None), "target", None)
            if victim is None:
                return
            if ref.endswith("s0"):
                # "Shift 1 square to a square adjacent to an enemy. You
                # then gain combat advantage against that enemy."
                #
                # **`c.grants_advantage(on=victim)` and not
                # `c.gains_advantage`.** The two read opposite ways: the
                # second takes a predicate and says *this* creature has
                # advantage whenever it holds, where the printed clause is
                # about one named enemy giving it up. `c.has_advantage`
                # does not exist, which is what the first draft reached
                # for.
                c.shift(1, who=me, toward=victim)
                c.grants_advantage(on=victim, until=When.EONT)
                return
            if ref.endswith("s1"):
                c.push(2, on=victim)
                c.shift(2, who=me)
                return
            # "...and the target is adjacent to you": the immobilise and
            # the advantage both hang on that, so it is one gate.
            if not c.adjacent(victim):
                return
            c.immobilized(on=victim, until=When.EONT)
            c.grants_advantage(on=victim, until=When.EONT)

        c.watch(PowerResolved, rider, until=When.ENCOUNTER, on=me,
                label=c.ref)

    row.__name__ = "knight_benefit_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One benefit: with {' or '.join(sorted(groups))}, {what}.\n\n"
        "The group is read when the strike resolves rather than when the "
        "trait arms -- a knight carries more than one weapon and nothing "
        "stops it swapping mid-turn."
    )
    return row


knight_benefit_0 = _benefit(
    "cf:fighter-knight-f9s0", ("heavy blade",),
    "shift 1 toward the target and gain combat advantage against it")
knight_benefit_1 = _benefit(
    "cf:fighter-knight-f9s1", ("staff",),
    "push the target 2 and shift 2")
knight_benefit_2 = _benefit(
    "cf:fighter-knight-f9s2", ("hammer",),
    "immobilise an adjacent target and gain combat advantage against it")


@power(
    "cf:fighter-knight-f11",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_shield_the_line(c: Cast) -> None:
    """"You gain the p12677 power."

    **A real grant, and the one that makes the rule here measurable.**
    `p12677` is `cls="fighter"` exactly as `p12660`, `p12661` and `p12668`
    are -- and `loadout` does **not** deal it, because it is not a level-0
    row. So "is it a power of this class" is not the test for whether a
    grant matters; the level is. Measured per ref rather than reasoned
    about, which is `#1259`'s whole point.
    """
    c.grant_row("p12677", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:fighter-knight-f17",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_valour(c: Cast) -> None:
    """"When you use your second wind or take the total defense action, you
    activate an aura 1 that lasts until the end of your next turn. While in
    the aura, each ally gains a +2 power bonus to all defenses."

    **Two printed triggers, so two watches**, which is `content/CLAUDE.md`'s
    rule stated the other way round: half of an "or" declared looks
    finished and is not. `SecondWind` and `TotalDefence` are both events and
    both carry `actor`.

    The aura is laid with `c.aura` and the modifiers go on whoever is
    inside via `aura_ring`, which handles the half a plain aura cannot: it
    takes the bonuses **off** again when an ally steps out, and its own
    ending unsubscribes before announcing the exits so the modifiers come
    off from `on_end`.

    `side="ally"` and four separate `c.bonus` calls, because *"all
    defenses"* is four keys and one call pays one of them. `kind="power"`
    because the card prints the word -- so two knights' auras do not
    stack, which is the rule that word exists for.

    `When.EONT` is *"until the end of your next turn"*, clocked on the
    knight.
    """
    me = c.me
    laid: set[int] = set()

    def raise_aura(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if me in laid:
            return
        laid.add(me)
        hold = c.effect(c.ref, until=When.EONT, on=me)
        if hold is None:
            return

        def give(who: int) -> list[Any]:
            if team(c.world, who) is not team(c.world, me) or who == me:
                return []
            return [c.bonus(d, 2, on=who, until=When.EONT, kind="power")
                    for d in DEFENCES]

        aura_ring(c, hold, side="ally", give=give)

    for event in (SecondWind, TotalDefence):
        c.watch(event, raise_aura, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:fighter-knight-f19",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_endurance(c: Cast) -> None:
    """"When you use your second wind, you can spend an additional healing
    surge."

    A `SecondWind` watch and `c.spend_surge`, which is the verb for exactly
    this -- it spends the surge and heals, and returns False when there is
    none left, so the clause declines itself on an empty pool rather than
    pretending.

    *"You can"* is `c.may`, so declining is one of the answers: a surge is
    a resource that has to last the day and a knight at full health after
    its second wind has nothing to buy.
    """
    me = c.me

    def again(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if c.may("spend a second healing surge"):
            c.spend_surge(on=me)

    c.watch(SecondWind, again, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:fighter-knight-f21",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def knight_indomitable(c: Cast) -> None:
    """An extra saving throw at the start of the knight's turn.

    `cf:fighter-slayer-f17`'s sentence word for word, so it is the same
    call: `c.save(when_="start")`, which does not replace the ordinary
    end-of-turn save -- the engine rolls that regardless, so the printed
    second sentence needs nothing written.

    Written out rather than shared, for `cf:rogue-thief-f1`'s reason.
    """
    me = c.me

    def early_save(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        c.save(on=me, when_="start")

    from combat_engine.engine.events import TurnStart

    c.watch(TurnStart, early_save, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the five rungs that supersede a lower number ----------------------------


def _rung(ref: str, what: str, into: str) -> Any:
    """One rung refused for want of a level.

    Three here, each written into the row whose number it raises. They
    shared one symbol because it was one gap three times, and a level map
    with a reader paid all three at once.
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
        implemented_in=(into,),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "knight_rung_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        f"**Written into `{into}`**, which is where a clause raising "
        "another row's number has to go -- no modifier can reach into "
        "that row's own call. So this is a pointer and carries "
        "`implemented_in=`, exactly as a feat naming one power does.\n\n"
        "What made it unwritable was the level, not a verb: every class "
        "feature armed at the start of every fight because "
        "`class_feature` carries none, so this number reached a 1st-level "
        "knight. `combat_engine.levels` carries the printed levels now "
        "and `chargen.ladder_row` reads them. `#1261`."
    )
    return row


knight_rung_12 = _rung("cf:fighter-knight-f12",
                       "`-f7`'s initiative bonus rises to +4.",
                       "cf:fighter-knight-f7")
knight_rung_14 = _rung("cf:fighter-knight-f14",
                       "`-f8`'s damage bonus rises to +2.",
                       "cf:fighter-knight-f8")
knight_rung_20 = _rung("cf:fighter-knight-f20",
                       "`-f8`'s damage bonus rises to +3.",
                       "cf:fighter-knight-f8")


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

    row.__name__ = "knight_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p12668` per encounter, still only once a turn.\n\n"
        "The same two gaps `cf:fighter-slayer-f3` names and the same two "
        "symbols -- the level is `#1261`'s, and nothing raises an existing "
        "row's per-encounter ceiling."
    )
    return row


knight_extra_use_6 = _extra_use("cf:fighter-knight-f6")
knight_extra_use_13 = _extra_use("cf:fighter-knight-f13")


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

    row.__name__ = "knight_another_stance_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "One more fighter stance, chosen at creation.\n\n"
        "`chargen.power_choice()`'s gap, as `cf:fighter-slayer-f6` is. No "
        "level symbol: an extra choice at creation is not wrong early the "
        "way a superseding number is."
    )
    return row


knight_another_stance_10 = _another_stance("cf:fighter-knight-f10")
knight_another_stance_16 = _another_stance("cf:fighter-knight-f16")


# -- the six rows the import cannot supply -----------------------------------


def _defective(ref: str, why: str) -> Any:
    """One of the six rows whose printed text is missing what it names."""

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

    row.__name__ = "knight_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


_NO_LIST = ("the spec reads 'you gain {n} of the following powers of your "
            "choice' and then lists nothing, so there is no set to choose "
            "from")

knight_defect_15 = _defective(
    "cf:fighter-knight-f15",
    "the spec reads 'you gain the cf:fighter-knight-f15 power' -- the "
    "feature names itself as the power it grants, and no such ref exists",
)
knight_defect_18 = _defective(
    "cf:fighter-knight-f18",
    "the spec names the granted power by its printed name instead of a "
    "ref, so the importer did not resolve it and there is nothing to "
    "grant -- the same shape as cf:fighter-slayer-f13",
)
knight_defect_22 = _defective("cf:fighter-knight-f22", _NO_LIST.format(n="two"))
knight_defect_23 = _defective("cf:fighter-knight-f23", _NO_LIST.format(n="one"))
knight_defect_24 = _defective("cf:fighter-knight-f24", _NO_LIST.format(n="one"))
knight_defect_25 = _defective("cf:fighter-knight-f25", _NO_LIST.format(n="one"))
