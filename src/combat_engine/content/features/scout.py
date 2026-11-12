"""The scout, the ranger's second chassis.

`#642`'s wave. 33 printed rows, and the one where **the class of a granted
ref finally decides the answer** rather than the level:

    -f1   p13619  cls="ranger",  level 0  dealt     -> no-op
    -f2   p12668  cls="FIGHTER", level 0  NOT dealt -> real
    -f6   p13600  cls="ranger",  level 5  NOT dealt -> real

The knight established the level is the test where the class is constant.
`-f2` is the other half: `p12668` is the fighter's power strike, which the
slayer and the knight both grant as a no-op and a ranger has to be handed.
So neither the class nor the level is the test on its own -- *is this ref
in the hand* is, which is why every one of these is measured.

The shape:

    13  play
     4  a ladder rung superseding a lower number -- `#1261`
     2  another use of `p12668` per encounter
     4  a knack or an aspect of the wild, chosen at creation
     1  "two of the following abilities" -- a fork that deals TWO
     6  `defect=`: "one of the following powers" and no list
     4  rows a fight has no use for -- `out_of_combat=True`

## Two off-hand forks, and they are not the same choice

`-f3` chooses between a light blade and an axe in the off hand, and `-f21`
chooses between the same two **again** at a much later level. The printed
text of `-f21` keys its benefit on *"your choice of off-hand weapon"*,
which reads like `-f3`'s answer -- and it is not: what both really gate on
is **what is in the off hand right now**, which a character can change.

So neither fork reads the other's `chargen.BUILD_OPTIONS` answer the way
the blackguard's four vice parents read `-f3`'s. Both read `Gear.off`.
`-f21` keeps its own entry because the two benefits differ and a scout
carrying an axe should get the axe one from both.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import _weapon_attack
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    Ability,
    ActionType,
    Cast,
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import PowerResolved, SecondWind, TotalDefence

#: The two rows the chassis is built around: its own at-will strike and the
#: fighter's power strike, which `-f2` has to hand over.
TWIN = "p13619"
STRIKE = "p12668"

#: "A light blade" and "an axe", as `Weapon.group` spells them.
BLADE = "light blade"
AXE = "axe"


def _off_hand(c: Cast) -> str:
    """What group is in the off hand, or `""`.

    **`Gear.off` and not `Gear.main`.** Every off-hand clause on this
    chassis is about the *second* weapon, and a two-blade ranger's main
    hand holds one of the same groups -- so reading `main` would answer
    True for a scout wielding two axes and one axe alike, and the fork
    would stop meaning anything.
    """
    gear = c.world.get(c.me, Gear)
    spare = gear.off if gear is not None else None
    return spare.group if spare is not None else ""


def _a_weapon_attack(c: Cast) -> Any:
    """"Weapon attack rolls" / "weapon damage rolls" -- the keyword on the
    row that is rolling, asked through `strikers._weapon_attack`."""
    me, world = c.me, c.world
    return lambda ctx: _weapon_attack(world, me, ctx) is not None


# -- the thirteen rows that play ---------------------------------------------


@power(
    "cf:ranger-scout-f0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_dexterity(c: Cast) -> None:
    """"When you make a melee basic attack, you can use your Dexterity
    modifier instead of your Strength modifier for the attack roll and the
    damage roll."

    `c.rolls_with` and one call pays both halves -- `Attack.ability_for`
    reads the swap before the header and `mba`'s body reads
    `c.attack_mod`. No weapon gate: the card puts none on this one, unlike
    `cf:rogue-thief-f3`'s version of the same sentence.

    This is the row `cf:assassin-executioner-f2s2` names from the other
    side -- its third guild says the scout's feature *"also applies to
    shuriken"* -- so it is a forward reference that now resolves, and that
    guild's dropped clause is about proficiency rather than about this.
    """
    c.rolls_with("mba", Ability.DEX, on=c.me, until=When.ENCOUNTER)


def _grant(ref: str, got: str, why: str) -> Any:
    """One of the three "you gain <power>" rows.

    The one helper the global rule allows, for three rows that share a
    shape. `why` is the measurement, because on this chassis the three
    answers come from three different reasons and a reader needs to see
    which.
    """

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "scout_grant_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f'"You gain the `{got}` power."\n\n{why}'
    return row


scout_grant_1 = _grant(
    "cf:ranger-scout-f1", TWIN,
    "A no-op grant: a level-0 **ranger** row, so `chargen.loadout` has "
    "already dealt it and `c.grant_row` returns `None`. `#1259`.")
scout_grant_2 = _grant(
    "cf:ranger-scout-f2", STRIKE,
    "**A real grant, and the class is why.** `p12668` is "
    '`cls="fighter"` -- the Essentials martial classes share one power '
    "strike and the fighter's page printed it first -- so `loadout` deals "
    "it to a fighter and not to a ranger. `cf:fighter-slayer-f1` and "
    "`cf:fighter-knight-f2` grant this same ref as a no-op.")
scout_grant_6 = _grant(
    "cf:ranger-scout-f6", "p13600",
    "**A real grant, and the level is why.** `p13600` is "
    '`cls="ranger"` like `p13619` beside it and `loadout` does not deal '
    "it, because `loadout` deals level-0 rows and this is level 5. The "
    "knight's `-f11` is the same lesson.")


@power(
    "cf:ranger-scout-f3",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_off_hand(c: Cast) -> None:
    """*"Gain `cf:ranger-scout-f3s0` or `cf:ranger-scout-f3s1`."*

    A **parent**, so `chargen.ladder_row` deals it and it chooses between
    its own two options. `chargen.BUILD_OPTIONS` and not a leg: the
    ranger's five legs are the base class's fork and a character takes one.
    """
    chose = (c.chosen_option("cf:ranger-scout-f3")
             or "cf:ranger-scout-f3s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


def _off_hand_bonus(ref: str, group: str, what: str, amount: int) -> Any:
    """One of `-f3`'s two options: a standing bonus behind an off-hand
    weapon group.

    Two rows, one shape. Each call names its own group, its own key and its
    own number.

    **The off hand is read live, in the `when=`.** A scout can change what
    is in that hand -- `cf:fighter-slayer-f4`'s free swap is on another
    chassis but the ranger has two hands full by design -- and measuring
    at arming would pay the bonus for a whole encounter after the weapon
    went away.
    """

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        me = c.me
        weapon = _a_weapon_attack(c)
        c.bonus(what, amount, on=me, until=When.ENCOUNTER, kind="untyped",
                when=lambda ctx: weapon(ctx) and _off_hand(c) == group)

    row.__name__ = "scout_off_hand_" + ref.rsplit("s", 1)[-1]
    article = "a" if group == BLADE else "an"
    row.__doc__ = (
        f'"+{amount} to weapon {what} rolls while you wield {article} '
        f'{group} in your off hand."\n\n'
        "Untyped: a class feature stacks with everything and the card "
        "prints no type word. The helper above has the argument for "
        "reading the off hand live."
    )
    return row


scout_off_hand_0 = _off_hand_bonus(
    "cf:ranger-scout-f3s0", BLADE, "attack", 1)
scout_off_hand_1 = _off_hand_bonus(
    "cf:ranger-scout-f3s1", AXE, "damage", 2)


@power(
    "cf:ranger-scout-f9",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_improved_twin(c: Cast) -> None:
    """"You gain a +2 bonus to damage rolls with your p13619 power."

    Gated on the **row being used** rather than on a weapon: `ctx["power"]`
    is the ref, so one comparison is the whole clause. That is what makes
    this different from `-f3s1`'s +2, which is about what is in a hand.

    **The ladder `-f10` and `-f14` climb is written here**: both print
    *"increases to"*, so they are pointers carrying `implemented_in=` and
    this body reads them. Rising order and plain `if`, so the highest held
    replaces rather than adds.
    """
    bonus = 2
    if c.feat("cf:ranger-scout-f10"):
        bonus = 4
    if c.feat("cf:ranger-scout-f14"):
        bonus = 6
    c.bonus("damage", bonus, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: ctx.get("power") == TWIN)


@power(
    "cf:ranger-scout-f12",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_wary(c: Cast) -> None:
    """"Whenever you use your second wind or take the total defense action,
    you can shift 1 square as a free action before or after doing so."

    **Two printed triggers, so two watches** -- the same pair
    `cf:fighter-knight-f17` answers, with a different effect. Half of an
    "or" declared looks finished and is not, which is what
    `content/CLAUDE.md` says about this exact shape.

    *"Before or after"* is not modelled and needs no marker: both watches
    fire after the event, and a 1-square shift taken a moment later ends on
    the same square it would have. The card offers the order as a
    convenience, not as a different outcome -- the one case where it would
    differ is a shift *out* of a square you are about to be attacked in,
    and neither event is an attack.

    *"You can"* is `c.may`, so declining is one of the answers.
    """
    me = c.me

    def step(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if c.may("shift a square"):
            c.shift(1, who=me)

    for event in (SecondWind, TotalDefence):
        c.watch(event, step, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:ranger-scout-f15",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_nimble(c: Cast) -> None:
    """"Whenever you shift, you can shift 1 additional square."

    `c.extend_every("shift", 1)` and not `c.extend_move`, and the
    difference is the whole clause. `extend_move` lengthens **one named
    row** and requires that row's body to read `c.squares_for` -- *"a
    modifier nothing consults is this component's commonest bug"*, its own
    docstring says. `extend_every` is keyed on the **move kind**, which the
    movement verb knows and the row does not, and `c.shift` consults it
    unconditionally at `cast.py`'s `_extra_every(mover, "shift")`.

    So this needs no row anywhere to cooperate, which is what *"whenever
    you shift"* requires -- the shifts a scout takes come from its own
    rows, from other people's rows, and from `-f12` above.

    Written although it is a late rung, on `features/thief.py`'s line: it
    supersedes nothing.
    """
    c.extend_every("shift", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:ranger-scout-f21",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_mastery(c: Cast) -> None:
    """Two clauses: another use of `p12668`, and a second off-hand fork.

    **Both now written, so no marker.** The fork half always played --
    this is a parent granting one of two declared options -- and the
    first sentence, *"you gain one more use of power strike per
    encounter"*, waited on the two gaps `cf:fighter-slayer-f3` named.
    `c.more_uses` is one and `combat_engine.levels` is the other.

    **This fork does not read `-f3`'s answer**, which is the opposite call
    from the blackguard's four vice parents and worth the line. Both forks
    gate on *what is in the off hand*, which a character can change, so
    neither is a record of a choice made at creation -- and the two
    benefits differ, so a scout carrying an axe should get the axe benefit
    from both rather than whichever one it picked at 1st level.
    """
    c.more_uses("p12668", 1, on=c.me)
    chose = (c.chosen_option("cf:ranger-scout-f21")
             or "cf:ranger-scout-f21s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:ranger-scout-f21s0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_mastery_axe(c: Cast) -> None:
    """"While you wield an axe in your off hand, your p12668 deals 3 extra
    damage to the target."

    A flat rider on one named row, so it is a `c.bonus` with a `power`
    gate rather than a watch -- `ctx["power"]` is the ref and the off hand
    is read live beside it, which is `-f3s0`'s arrangement.

    Three, not `3 + anything`: the card prints a bare number.
    """
    c.bonus("damage", 3, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: (ctx.get("power") == STRIKE
                              and _off_hand(c) == AXE))


@power(
    "cf:ranger-scout-f21s1",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_mastery_blade(c: Cast) -> None:
    """"While you wield a light blade in your off hand, you can take a free
    action to shift up to 3 squares immediately after using p12668."

    A `PowerResolved` watch, which is what *"immediately after using"*
    means -- `cf:rogue-thief-f16` takes the same shape for the same
    sentence about a different row, and `cf:paladin-blackguard-f20` for a
    teleport.

    The off hand is read **when the strike resolves**, not when the trait
    arms, for the reason `-f3`'s options give: a ranger's second hand is
    the one the chassis is about and nothing stops it changing.

    `who=` and not `on=`: `c.shift` spells the creature `who`, as
    `c.teleport` does and `c.slide` does not. Getting it wrong is a
    `TypeError` at fire time rather than at import, which on
    `cf:rogue-thief-f16` was invisible until the triggering row was
    audited.
    """
    me = c.me

    def step(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if getattr(ev, "power", "") != STRIKE:
            return
        if _off_hand(c) != BLADE:
            return
        if c.may("shift away"):
            c.shift(3, who=me)

    c.watch(PowerResolved, step, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:ranger-scout-f17s0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.on_check(skill=)",),
)
def scout_group_stealth(c: Cast) -> None:
    """"Whenever you make a Stealth check, each ally within 10 squares of
    you gains a +2 bonus to his or her next Stealth check before the end of
    your next turn."

    The effect half is writable -- `c.bonus("skill:stealth", 2, on=ally,
    once=True)` is every piece of it -- and the **trigger** is not: nothing
    watches a skill check being made. `c._stealth_hide` rolls one and
    emits no event a row can answer, so there is no door.

    One symbol, naming the watch rather than the bonus, because the bonus
    is not what is missing.
    """


# -- the four ladder rungs --------------------------------------------------


def _rung(ref: str, what: str, into: str) -> Any:
    """One rung refused for want of a level. Four here, one symbol."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        implemented_in=(into,),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "scout_rung_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        f"**Written into `{into}`**, which is where a clause raising "
        "another row's number has to go -- no modifier can reach into "
        "that row's own `c.bonus` call. So this is a pointer and "
        "carries `implemented_in=`, exactly as a feat naming one power "
        "does.\n\n"
        "What made it unwritable was the level, not a verb: every "
        "class feature armed at the start of every fight because "
        "`class_feature` carries none, so this number reached a "
        "1st-level character. `combat_engine.levels` carries the "
        "printed levels now and `chargen.ladder_row` reads them. "
        "`#1261`."
    )
    return row


scout_rung_10 = _rung("cf:ranger-scout-f10",
                      "`-f9`'s damage bonus rises to +4.",
                      "cf:ranger-scout-f9")
scout_rung_14 = _rung("cf:ranger-scout-f14",
                      "`-f9`'s damage bonus rises to +6.",
                      "cf:ranger-scout-f9")


def _extra_use(ref: str) -> Any:
    """The row granting another use of `p12668` per encounter."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.more_uses("p12668", 1, on=c.me)

    row.__name__ = "scout_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p12668` per encounter, still only once a turn.\n\n"
        "**Both halves landed.** `c.more_uses` raises an existing row's "
        "per-encounter allowance, and `combat_engine.levels` carries the "
        "printed level so `chargen.ladder_row` deals this rung when the "
        "page says. `#1261`.\n\n"
        "`p12668` and not `p13619`: the scout's own strike is the twin, "
        "and the sentence raises the FIGHTER's power strike, which `-f2` "
        "is the row that grants."
    )
    return row


scout_extra_use_4 = _extra_use("cf:ranger-scout-f4")


# -- the four choices at creation -------------------------------------------


def _pick(ref: str, what: str) -> Any:
    """One of the four "one additional knack / aspect of the wild" rows."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        todo=("chargen.power_choice()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "scout_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        "`chargen.power_choice()`'s gap -- a draw from a named printed "
        "family. No level symbol: an extra choice at creation is not wrong "
        "early the way a superseding number is."
    )
    return row


scout_pick_5 = _pick("cf:ranger-scout-f5", "One more wilderness knack.")
scout_pick_7 = _pick("cf:ranger-scout-f7", "One more aspect of the wild.")
scout_pick_8 = _pick("cf:ranger-scout-f8",
                     "One more wilderness knack, from 1st level's options.")
scout_pick_11 = _pick("cf:ranger-scout-f11", "One more aspect of the wild.")


@power(
    "cf:ranger-scout-f17",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("chargen.BUILD_OPTIONS(pick=2)",),
)
def scout_abilities(c: Cast) -> None:
    """*"You gain **two** of the following abilities of your choice."*

    A fork that deals **two**, and `chargen.BUILD_OPTIONS` deals one.
    That is the whole gap and it is a new one: `deal_build_option` draws a
    single ref, `c.chosen_option` returns a single ref, and every other
    parent in this wave picks one. Five options are declared below, so the
    content is here and what is missing is the arity.

    Not approximated by dealing one, which would quietly give a scout half
    its feature; and not by granting all five, which is strictly stronger
    than print. Either half is wrong, so the row waits.

    `-f17s0` carries a gap of its own on top -- see it -- and the other
    four are skill clauses the story engine owns.
    """


def _narrative(ref: str, what: str, why: str) -> Any:
    """One of `-f17`'s four abilities that a fight has no use for.

    **`out_of_combat=True` and not `narrative=`, and the audit is what
    said so.** `narrative=` marks *one clause* of a row that otherwise
    plays; `out_of_combat=True` marks a **row** that is complete and inert
    in a fight. These four have no second clause, so the second is the
    marker -- and `dsl.power` refuses both together, so it is a choice.

    Written as `narrative=` first, and the sweep reported all four as
    **newly silent** rather than excusing them: `audit` credits an
    `out_of_combat` row as *"silent on a board as claimed"* and has no such
    excuse for a narrative one, because a narrative row is supposed to have
    a combat half. Four rows of known-silence debt for using the
    clause-level marker on a whole row.

    Distinguished from `-f17s0`, which **does** have combat meaning (a
    Stealth check decides who is hidden) and so takes a symbol.

    The decorator is still applied by hand rather than as `@power`, which
    `narrative=` forced and `out_of_combat` does not -- kept because
    `row.__doc__` is built per call either way and one order is easier to
    read than two.
    """

    def row(c: Cast) -> None:
        pass

    row.__name__ = "scout_ability_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One of `-f17`'s abilities: {why}\n\n"
        f"`out_of_combat=True`: the whole row is a {what} check and what "
        "it changes happens outside a fight -- there is no board state it "
        "reads and none it writes. A clause the engine is merely missing "
        "would be `dropped=`; this row is finished.\n\n"
        "Empty rather than a `c.note`: a trait runs at the start of every "
        "fight and a line in the log would announce something that is not "
        "happening, which is `cf:druid-f2`'s reasoning."
    )
    return power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        out_of_combat=True,
    )(row)


scout_ability_1 = _narrative(
    "cf:ranger-scout-f17s1", "diplomacy",
    "a bonus to social checks against beasts, and simple commands they "
    "are under no compulsion to obey.")
scout_ability_2 = _narrative(
    "cf:ranger-scout-f17s2", "athletics",
    "a climb the scout succeeds at becomes easier for the allies who "
    "watched it.")
scout_ability_3 = _narrative(
    "cf:ranger-scout-f17s3", "perception",
    "the party sleeps through an extended rest without the usual penalty.")
scout_ability_4 = _narrative(
    "cf:ranger-scout-f17s4", "perception",
    "a short-rest sweep of the surrounding area for what has passed "
    "through it.")


@power(
    "cf:ranger-scout-f13",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def scout_keen_eye(c: Cast) -> None:
    """"Whenever you make a Perception check, you can roll twice and use
    either result."

    `c.roll_twice` is the whole of it -- the verb
    `cf:rogue-thief-f20` defined, since both cards print the same sentence
    and neither narrows by action. `Powers.rolls_twice` is the store and
    `skills.check` the single reader.

    Not `narrative=`: a Perception check decides what a scout notices
    before a fight starts and whether it is surprised, which is combat
    meaning -- and now it has a writer.
    """
    c.roll_twice("perception", on=c.me)


# -- the six rows the import cannot supply -----------------------------------


def _defective(ref: str, n: str) -> Any:
    """One of the six "one of the following powers" rows with no list."""

    why = (f"the spec reads 'you gain {n} of the following powers of your "
           "choice' and then lists nothing, so there is no set to choose "
           "from")

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "scout_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


scout_defect_16 = _defective("cf:ranger-scout-f16", "two")
scout_defect_18 = _defective("cf:ranger-scout-f18", "one")
scout_defect_19 = _defective("cf:ranger-scout-f19", "one")
scout_defect_20 = _defective("cf:ranger-scout-f20", "one")
scout_defect_22 = _defective("cf:ranger-scout-f22", "one")
scout_defect_23 = _defective("cf:ranger-scout-f23", "one")
