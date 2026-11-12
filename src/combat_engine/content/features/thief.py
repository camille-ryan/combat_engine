"""The thief, the rogue's second chassis.

`#642`'s wave. 26 printed rows, and the cheapest chassis in the wave so far
because **the rogue's machinery is all in `strikers.py` already**: the
scoundrel's extra damage, its weapon gate, its once-a-turn latch and the
feats that trade a die of it. Two of the thief's rows are the scoundrel's
word for word, and one of them says so on the card -- *"see the
`cf:rogue-scoundrel-f4` table"* -- so the cross-reference is made literal
rather than copied.

## How a row with no printed level is handled here, which is a line

`#1261`: `class_feature` has no level column, so no row in this tree knows
what level it arrives at. Nine of the thief's 26 are ladder rungs. The line
drawn, and it is drawn rather than discovered:

* **A rung that supersedes a lower one with a bigger number is NOT
  written.** `-f10`, `-f13` and `-f19` each raise `-f3`'s damage bonus, and
  all four rows arm at the start of every fight, so writing them pays a
  1st-level thief +5 where the card says +2. `chargen.feature_level()` is
  the symbol and it is one gap three times.
* **A rung that merely adds something, with no level in its own text, IS
  written.** `-f11`'s +2 to initiative and `-f21`'s +3 to skill checks are
  correct clauses whose *timing* is `#1261`'s problem, not theirs, and
  marking every such row would bury the gaps that are real. This is what
  every other chassis in the tree does today.

## Two kinds of row the compendium cannot supply

`-f14` and `-f17` print *"You gain the cf:rogue-thief-f14 power"* -- the
feature naming **itself** as the power it grants, which no ref resolves.
`-f22` through `-f25` print *"You gain two of the following powers of your
choice"* and then no list. Both are `defect=`: the source is missing what
the row would be written from, so no symbol will ever close them and
`todo=` would lie by naming one. `dsl.entry_of` returns a `cf:` ref
unchanged, so each refuses only itself and the chassis is unharmed --
checked, because on a monster one defective row defects the whole block.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import (
    _SNEAK_GROUPS,
    _light_blade_or_bow,
    _weapon_attack,
    extra_damage,
)
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    Ability,
    ActionType,
    Cast,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import has_combat_advantage

#: The trick `-f0` grants and `-f16` shifts after.
TRICK = "p12710"

#: The label the extra damage is paid under. **The scoundrel's**, which is
#: the printed cross-reference made literal: the card says *"see the
#: `cf:rogue-scoundrel-f4` table"*, and sharing the label shares the
#: once-a-turn latch, the `cf:rogue-tactic-*` bonuses keyed on it, and
#: `FORGO_A_DIE`'s `f952` trade. A character is a thief or a scoundrel and
#: never both, so one latch cannot be double-spent.
SNEAK = "cf:rogue-scoundrel-f4"


def _with_a_sneak_weapon(c: Cast) -> Any:
    """"With light blades, hand crossbows, shortbows, and slings" -- the
    same four arms the scoundrel's own gate names, asked of the weapon the
    swing is using.

    `_weapon_attack` and not the main hand: a rogue carries a blade and a
    shooter, and a bonus that read the main hand would pay a crossbow bolt
    for the dagger's sake. The groups come from `strikers._SNEAK_GROUPS`
    rather than a second list here, because they are the same printed four
    and two lists drift.
    """
    me, world = c.me, c.world

    def gate(ctx: dict[str, Any]) -> bool:
        weapon = _weapon_attack(world, me, ctx)
        if weapon is None:
            return False
        return weapon.is_light_blade or weapon.group in _SNEAK_GROUPS

    return gate


# -- the rows that play ------------------------------------------------------


@power(
    "cf:rogue-thief-f0",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_trick(c: Cast) -> None:
    """"You gain the p12710 power."

    A no-op grant: `p12710` is declared `cls="rogue"` at level 0, so
    `chargen.loadout` has already dealt it and `c.grant_row` returns
    `None`. Written out because `-f6`, `-f12` and `-f16` are all about that
    row and a reader following them needs to land somewhere. `#1259`.
    """
    c.grant_row(TRICK, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:rogue-thief-f1",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_first_strike(c: Cast) -> None:
    """"At the start of every encounter, you have combat advantage against
    any creatures that have not yet acted in that encounter."

    `cf:rogue-scoundrel-f0`'s sentence exactly, and written the same way
    for its reasons rather than a new reading of it: **one grant per
    creature** rather than one flag on the rogue, because the printed
    condition lapses when *that* creature acts and not when the round turns
    over. `When.SOTNT` clocks on the creature the effect sits on, so each
    grant ends at the start of that creature's first turn with no watcher
    to keep in step.

    The round is checked because `Encounter.join` arms a latecomer's traits
    too, and a thief walking into round five has caught nobody cold.

    Not shared with the scoundrel's row, and that is deliberate: a thief is
    not dealt `cf:rogue-scoundrel-f0` at all -- a named chassis supersedes
    the blank ladder -- so if this row did not pay the clause, nobody
    would. Compare `SNEAK` below, where sharing is right because the
    sharing is a **latch** and not a payment.
    """
    fight = c.world.encounter
    if fight is None or c.world.round > 1:
        return
    for other in fight.order:
        if other != c.me:
            c.grants_advantage(on=other, until=When.SOTNT)


@power(
    "cf:rogue-thief-f2",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_light_blade_or_bow,
    requires_text="needs a light blade, a crossbow or a sling",
)
def thief_sneak(c: Cast) -> None:
    """Once a turn, a hit on a creature granting you combat advantage hurts
    more -- *"based on your level (see the `cf:rogue-scoundrel-f4` table)"*.

    So the card itself says this is that row's table, and the
    implementation says it the same way: `extra_damage` with the
    **scoundrel's label**. What that buys, none of which would work from a
    label of this row's own:

    * the once-a-turn latch is one latch, so the two cannot both pay;
    * `f952`'s *"forgo one die for -2 to its attacks"* is registered
      against that label in `FORGO_A_DIE`, and a thief holding the feat
      gets it;
    * anything that raises `"cf:rogue-scoundrel-f4 damage"` is read here
      too.

    Per **turn** and not per round, which is this card's word as it is the
    scoundrel's -- so a thief pays again on an opportunity attack in a
    round it has already paid in.

    Combat advantage is asked of the board at the moment of the hit rather
    than stored, for `query`'s own reason: flanking ends the instant an
    ally steps away and a stored flag would not notice.
    """
    extra_damage(
        c,
        "2d6",
        applies=lambda target: has_combat_advantage(c.world, c.me, target),
        label=SNEAK,
        per_turn=True,
    )


@power(
    "cf:rogue-thief-f3",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_dexterity(c: Cast) -> None:
    """Dexterity for a melee basic attack, and +2 damage with the four arms.

    *"When you make a melee basic attack, you can use Dexterity instead of
    Strength for the attack roll and the damage roll."* `c.rolls_with` pays
    both halves in one call -- `Attack.ability_for` reads the swap before
    the header and `mba`'s body reads `c.attack_mod`. No weapon gate: the
    card puts none on this half, unlike the one below.

    *"In addition, you gain a +2 bonus to damage rolls with light blades,
    hand crossbows, shortbows, and slings."* Untyped, because the card
    prints no type word, and gated on the weapon the swing is **using**
    rather than the main hand -- a rogue carries a blade and a shooter.

    **The +2 is the first rung of a ladder three other rows climb, and
    those three are written here**: `-f10`, `-f13` and `-f19` each print
    *"increases to"*, so they are pointers carrying `implemented_in=` and
    this body reads which are held. Rising order and plain `if`, so the
    highest held replaces rather than adds -- a 19th-level thief holds all
    three and the page says +5, not +3+4+5.
    """
    me = c.me
    c.rolls_with("mba", Ability.DEX, on=me, until=When.ENCOUNTER)
    bonus = 2
    if c.feat("cf:rogue-thief-f10"):
        bonus = 3
    if c.feat("cf:rogue-thief-f13"):
        bonus = 4
    if c.feat("cf:rogue-thief-f19"):
        bonus = 5
    c.bonus("damage", bonus, on=me, until=When.ENCOUNTER, kind="untyped",
            when=_with_a_sneak_weapon(c))


@power(
    "cf:rogue-thief-f4",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.gains_training()", "story.auto_success_on_20()"),
)
def thief_skills(c: Cast) -> None:
    """An extra trained skill off a printed list of six, and a natural 20 on
    a skill challenge check counting double.

    Two clauses, two gaps, two symbols -- the row has nothing that plays,
    so `todo=` rather than `dropped=`.

    `c.gains_training()` is the symbol `cf:wizard-witch-f1s0` and its
    sibling already wait on: `vocab.py --find training` returns `c.check`
    and `c.substitute_check` and no granter, `chargen` deals training, and
    nothing adds to it. `#1258` carries the question of whether a row
    should be able to.

    The second is the story engine's and not the kernel's. A skill
    challenge counts successes against a target; *"that check automatically
    succeeds and counts as one additional success"* needs the runner to
    read a natural 20 and credit two, and `story/` has no hook a row can
    reach. Its own symbol because a row waiting on both would report ready
    the day either landed.
    """


@power(
    "cf:rogue-thief-f5",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_accuracy(c: Cast) -> None:
    """"You gain a +1 bonus to attack rolls with light blades, hand
    crossbows, shortbows, and slings."

    The same four arms as `-f3`'s second clause and the same gate, so it
    reads `_with_a_sneak_weapon` rather than a copy. Untyped: a class
    feature stacks with everything and the card prints no type word.

    Gated on the weapon the swing is **using**, which is the whole value of
    `_weapon_attack` -- installed once on the strength of what was in hand
    when the fight began, this would pay a thief's greatclub.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_with_a_sneak_weapon(c))


@power(
    "cf:rogue-thief-f8",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_second_trick(c: Cast) -> None:
    """"You gain the p12722 power."

    A no-op grant of the same kind as `-f0`: `p12722` is a level-0 rogue
    row, so every rogue has been dealt it.
    """
    c.grant_row("p12722", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:rogue-thief-f11",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_initiative(c: Cast) -> None:
    """"You gain a +2 bonus to initiative."

    **`c.initiative`, not `c.bonus("initiative", ...)`.** `Initiative.bonus`
    is summed before the d20 and `Mods` is never consulted, so the modifier
    would be laid and no roll would read it -- which `f2565`'s own comment
    in `general_l.py` records, and is the kind of silently-false thing
    `docs/AUTHORING.md` exists for.

    Written although it is a ladder rung, on the line the module docstring
    draws: the clause supersedes nothing and is correct whenever it
    applies, so what `#1261` costs here is that a 1st-level thief has it
    early rather than that the row is wrong.

    **`audit` reports this row SILENT and it works.** `adjust_initiative`
    bumps `Initiative.rolled` and re-splices the order, and it emits
    nothing, so there is no event for `audit._claimed` to credit -- a row
    whose *whole* content is an initiative bump is silent by construction.
    `f2565` is the same call and audits green only because it lays a save
    bonus beside it, which masks this.

    Measured rather than argued, on the audit board:
    `Initiative.rolled` 10 -> 12 and the thief moves from slot 5 to slot 4.
    `drivers.thief_chassis` asserts the slot, which is the observable the
    sweep has no access to. `#1262`.
    """
    c.initiative(2, on=c.me)


@power(
    "cf:rogue-thief-f16",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_withdraw(c: Cast) -> None:
    """"After you use p12710, you can immediately shift up to 3 squares as a
    free action."

    A watch on `PowerResolved` and not on the attack: *"after you use"* is
    satisfied by the trick having gone off, and `p12710` is itself a free
    action triggered **before** a basic attack, so reading the declaration
    would shift the thief away before the swing it bought.

    *"Up to 3 squares"* and *"can"* are both offers, so `c.shift` is handed
    the distance and the choice of going nowhere is one of the answers.
    A free action costs nothing the engine tracks, so no action is charged
    -- which is the card, not a shortcut: `c.extra_action` prices a minor
    or a move and there is nothing to price here.

    **`who=` and not `on=`.** `c.shift` is one of the handful of verbs that
    spells the creature `who`, and `on=` raises `TypeError` -- which the
    sweep caught only when `p12710` was audited, because auditing *this*
    row lays the watch and never fires it. A probe shows a pass is capable,
    not responsible.
    """
    me = c.me

    def withdraw(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if getattr(ev, "power", "") != TRICK:
            return
        c.shift(3, who=me)

    c.watch(PowerResolved, withdraw, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:rogue-thief-f21",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_mastery(c: Cast) -> None:
    """"You gain a +3 bonus to all skill checks."

    `"skill"` with no name after it is the key every skill check reads, so
    one call is the whole clause -- `c.bonus(f"skill:{name}", ...)` is the
    narrower form the witch's covens use and is the wrong one here.
    Untyped, because the card prints no type word.

    Written although it is the chassis's last rung, on the module
    docstring's line: it supersedes nothing.
    """
    c.bonus("skill", 3, on=c.me, until=When.ENCOUNTER, kind="untyped")


# -- the three rungs that cannot be written without a level ------------------
#
# Each raises `-f3`'s damage bonus, and all four rows arm at the start of
# every fight. One symbol, because they are one gap three times: a level
# column with a reader pays all three at once, and three symbols would make
# `blocked.py --group` report three.


def _damage_rung(ref: str, value: int) -> Any:
    """One rung of `-f3`'s damage ladder, refused for want of a level.

    The one helper the global rule allows, for a run of rows that genuinely
    share a marker -- three here, identical but for the number each raises
    the bonus to, and each call below names its own.
    """

    @power(
        ref,
        level=0,
        cls="rogue",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        implemented_in=("cf:rogue-thief-f3",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "thief_damage_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"`cf:rogue-thief-f3`'s damage bonus rises to +{value}.\n\n"
        "**Written into `cf:rogue-thief-f3`**, which is where a clause "
        "raising another row's number has to go -- no modifier can reach "
        "into that row's own `c.bonus` call. So this is a pointer and "
        "carries `implemented_in=`.\n\n"
        "What made it unwritable was the level, not a verb: every class "
        "feature armed at the start of every fight because "
        f"`class_feature` carries none, so a +{value} reached a 1st-level "
        "thief. `combat_engine.levels` carries the printed levels now and "
        "`chargen.ladder_row` reads them. `#1261`."
    )
    return row


thief_damage_10 = _damage_rung("cf:rogue-thief-f10", 3)
thief_damage_13 = _damage_rung("cf:rogue-thief-f13", 4)
thief_damage_19 = _damage_rung("cf:rogue-thief-f19", 5)


# -- the two rungs that add a use of the trick -------------------------------


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p12710` per encounter."""

    @power(
        ref,
        level=0,
        cls="rogue",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.more_uses("p12710", 1, on=c.me)

    row.__name__ = "thief_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p12710` per encounter, still only once a turn.\n\n"
        "Two gaps, two symbols. The level is `#1261`'s, as the damage rungs "
        "above. The allowance is its own: `chargen.EXTRA_GAINS` says what a "
        "feature **gains** at a level and nothing says what one adds to an "
        "existing row's uses, so `Powers.per_encounter` has no writer -- "
        "where `c.restore_use` hands one back and `c.regain_power` refreshes "
        "one, neither raises the ceiling.\n\n"
        "The *\"only once per turn\"* half needs nothing: `p12710` is a "
        "triggered free action and the turn limit is already how the trick "
        "behaves."
    )
    return row


thief_extra_use_6 = _extra_use("cf:rogue-thief-f6")
thief_extra_use_12 = _extra_use("cf:rogue-thief-f12")


# -- the three rows that deal another trick ----------------------------------


def _another_trick(ref: str) -> Any:
    """One of the three rows reading "you gain one additional rogue trick"."""

    @power(
        ref,
        level=0,
        cls="rogue",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        todo=("chargen.power_choice()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "thief_another_trick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "One more rogue trick, chosen at creation.\n\n"
        "A draw from a named printed family, which is the gap "
        "`chargen.power_choice()` names and four feats already wait on "
        "(`f3582`, `f3588`, `f3616`, `f3646`). The family exists here -- "
        "`p12710` and `p12722` are two of the tricks and both are written "
        "-- so unlike `cf:wizard-bladesinger-f1`'s cantrips this is the "
        "draw and nothing else.\n\n"
        "No level symbol, deliberately: an extra choice at creation is not "
        "wrong early the way a superseding number is, so `#1261` costs this "
        "row nothing a reader has to track."
    )
    return row


thief_another_trick_7 = _another_trick("cf:rogue-thief-f7")
thief_another_trick_9 = _another_trick("cf:rogue-thief-f9")
thief_another_trick_15 = _another_trick("cf:rogue-thief-f15")


# -- the two reroll rows -----------------------------------------------------


@power(
    "cf:rogue-thief-f18",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.roll_twice(check=)", "c.roll_twice(save=)"),
)
def thief_slippery(c: Cast) -> None:
    """"Whenever you make an Acrobatics check or an Athletics check as part
    of the escape action or make a saving throw against an effect that
    immobilizes, restrains, or slows you, you can roll twice and use either
    result."

    Two readers and therefore two symbols, and **`c.roll_twice` satisfies
    neither** -- which is worth saying now that the verb exists.

    `c.roll_twice` grants a second d20 on a **named skill**, and this card
    pays on Acrobatics and Athletics *as part of the escape action* only.
    Granting the skills outright would be wider than the card: a thief
    would roll twice on every climb. So the check half still needs the
    facility to know which **action** a check belongs to, and the symbol
    stays.

    The save half is a different roll entirely, in a different file, so it
    keeps its own symbol. A row waiting on one of the two would report
    ready with half of it built.

    `cf:rogue-thief-f20` beside it is the caller `c.roll_twice` was built
    for: same sentence, no action test.
    """


@power(
    "cf:rogue-thief-f20",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def thief_stealthy(c: Cast) -> None:
    """"Whenever you make a Stealth check or a Thievery check, you can roll
    twice and use either result."

    `c.roll_twice` is the whole of it, and this row is why that verb
    exists: it was the simpler of the two callers -- no action test -- so
    it is the one that defined the shape. `Powers.rolls_twice` is the
    store and `skills.check` the single reader.

    Measured rather than assumed: over 400 checks the mean natural goes
    from 10.58 to 14.10, against 13.825 for the best of two d20s.

    Not `narrative=`: Stealth is a combat check -- `c._stealth_hide` is the
    hide that rolls it -- so this row has a fight to be wrong in.
    """
    c.roll_twice("stealth", "thievery", on=c.me)


# -- the six rows the compendium cannot supply -------------------------------


def _defective(ref: str, why: str) -> Any:
    """One of the six rows whose printed text is missing what it names.

    `defect=` and not `todo=`/`dropped=`: no symbol will ever close these,
    because the gap is in the source. `usable` refuses the row and every
    chargen draw excludes it, which is the right outcome -- a feature
    granting a power nobody can identify is wrong in every fight rather
    than incomplete.

    `dsl.entry_of` returns a `cf:` ref unchanged, so each of these refuses
    **only itself**. Checked rather than assumed: on a monster one
    defective row defects the whole stat block, and a chassis losing its 26
    rows to one bad import would be a character nobody can be dealt.
    """

    @power(
        ref,
        level=0,
        cls="rogue",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "thief_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


thief_defect_14 = _defective(
    "cf:rogue-thief-f14",
    "the spec reads 'you gain the cf:rogue-thief-f14 power' -- the feature "
    "names itself as the power it grants, and no such ref exists",
)
thief_defect_17 = _defective(
    "cf:rogue-thief-f17",
    "the spec reads 'you gain the cf:rogue-thief-f17 power' -- the feature "
    "names itself as the power it grants, and no such ref exists",
)
thief_defect_22 = _defective(
    "cf:rogue-thief-f22",
    "the spec reads 'you gain two of the following powers of your choice' "
    "and then lists nothing, so there is no set to choose from",
)
thief_defect_23 = _defective(
    "cf:rogue-thief-f23",
    "the spec reads 'you gain one of the following powers of your choice' "
    "and then lists nothing, so there is no set to choose from",
)
thief_defect_24 = _defective(
    "cf:rogue-thief-f24",
    "the spec reads 'you gain one of the following powers of your choice' "
    "and then lists nothing, so there is no set to choose from",
)
thief_defect_25 = _defective(
    "cf:rogue-thief-f25",
    "the spec reads 'you gain one of the following powers of your choice' "
    "and then lists nothing, so there is no set to choose from",
)
