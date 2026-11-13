"""The bladesinger, the wizard's fourth written chassis and its largest.

`#642`'s wave. 24 printed rows, which is more than the arcanist, the mage
and the witch put together, and the reason is that **15 of them are the
spellbook ladder**: seven rows that add two encounter attack powers which
"function as daily attack powers", five that add two utilities, plus the
preparation mechanic, the cantrips and the bladespells. Nine rows have
combat meaning.

The plumbing was already here, which is what makes the chassis affordable.
`p14285` and all six bladespell at-wills are written in
`powers/wizard/level_0.py`, the bladespell trigger is
`_bladespell`/`BLADESPELL` there, and `_sword_hand` is the printed
one-handed-and-nothing-else requirement that four of these rows also ask.
So this file reaches for those rather than restating them, and the one
change it needed elsewhere was a bare labelled hold on `p14285` so that
*"while your `p14285` is active"* has something to read.

**The one marker worth explaining up front.** The seven "two encounter
attack powers, and the two function as dailies" rows share **one** symbol,
`chargen.spellbook(encounter_as_daily=)`, because they are one gap seven
times: `chargen.spellbook`'s own comment says an encounter *attack* power
is a slot the book has no say over, and nothing anywhere reinterprets a
row's usage per character. Seven symbols would report seven gaps and
`blocked.py --group` would stop being able to say how much work that is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.wizard.level_0 import _sword_hand
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    Ability,
    ActionType,
    Cast,
    Gear,
    Keyword,
    Powers,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.events import Hit, PowerResolved

#: The row `-f4` grants, whose bare hold two rows below read.
SONG = "p14285"

#: "A light blade or a heavy blade", as `Weapon.group` spells them.
BLADES = ("light blade", "heavy blade")

#: The armours "while you are wearing light armor or no armor" allows. The
#: empty string is what a creature with no `Gear` armour field is wearing.
UNARMOURED = ("", "cloth", "leather", "hide")


def _a_blade_in_one_hand(c: Cast, who: int | None = None) -> bool:
    """"A one-handed melee weapon ... that is a light blade or a heavy
    blade."

    Narrower than `_sword_hand`, which asks only that the hand be free: a
    bladesinger's chosen weapon is a *blade* specifically, and a one-handed
    mace in an empty hand satisfies `p14285`'s own requirement while
    satisfying none of this.
    """
    gear = c.world.get(c.me if who is None else who, Gear)
    if gear is None:
        return False
    weapon = gear.main
    return (
        weapon is not None
        and not weapon.ranged
        and not weapon.two_handed
        and weapon.group in BLADES
    )


def _one_handed_swing(world: Any, eid: int) -> bool:
    """"A weapon you wield in one hand", for `c.rolls_with`'s `(world, eid)`
    gate.

    Asked live rather than measured at arming, which is the whole value of
    the gate: a two-hander taken up mid-fight takes the swap away, and the
    same shape is what `cf:bard-skald-f0` uses for its Charisma swap.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and not weapon.two_handed


def _a_ranged_or_area_row(ctx: dict[str, Any]) -> bool:
    """"Your ranged attacks and area attacks", off the row that is rolling.

    `reach.kind` is where the printed line lives, and the two words are the
    two the card names -- a close burst is neither, which is the same
    distinction `controllers_sd._STRUCK` draws from the other side.
    """
    rolling = get(ctx.get("power") or "")
    return rolling is not None and rolling.reach.kind in ("ranged", "area")


def _spellbook_slots(ref: str, ceiling: str, what: str) -> Callable[[Cast], None]:
    """A run of rows that add two powers to the book.

    The one helper the global rule allows, and this is the case it is for:
    **twelve** rows whose whole printed text is "you add two new wizard
    <kind> powers ... to your spellbook", differing only in the ceiling on
    what may be chosen and in whether the two are utilities or encounter
    attacks reinterpreted as dailies. Each call below still names its own
    ceiling and its own kind out loud rather than deriving either.

    **`ceiling` is the card's own words and never a level this row was
    given.** The seven encounter rows each print one -- *"of 3rd level or
    lower"* -- and the five utility rows print *"of your level or lower"*
    and nothing else. The level at which each row is **gained** is not in
    the imported spec at all, for any of the 24; `class_feature.ord` is a
    plain index. So no number appears here that the page did not say, which
    is `#1261`.

    `what` decides the marker, and that is the whole distinction:

    * **utility** -- no marker. `chargen.spellbook` already stocks
      utilities (`slot is Usage.DAILY or p.attack is None`), so the book a
      bladesinger carries holds them and the row is the pointer that says
      so. `out_of_combat=True`, because owning a power is not a thing that
      happens in a fight.
    * **encounter-as-daily** -- one shared symbol. The book explicitly
      excludes encounter attack powers and nothing reinterprets a usage
      per character, so neither half of the printed sentence has a writer.
    """
    utility = what == "utility"

    @power(
        ref,
        level=0,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        out_of_combat=utility,
        todo=() if utility else ("chargen.spellbook(encounter_as_daily=)",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "bladesinger_book_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"Two more wizard {what} powers in the book, {ceiling}.\n\n"
        + (
            "Inert, and finished. `chargen.spellbook` stocks the book with "
            "the class's spare utilities, so this row is the pointer that "
            "says the slots exist rather than a second mechanism that "
            "fills them -- the same reading every *\"you gain <power>\"* "
            "row in this tree gets.\n\n"
            "Empty rather than a note: a trait runs at the start of every "
            "fight and a line in the log would announce something that is "
            "not happening."
            if utility
            else "Nothing is written, and the marker is shared with six "
            "siblings because they are one gap seven times. The book has "
            "no slot for an encounter *attack* power at all -- "
            "`chargen.spellbook` says so in a comment -- and the printed "
            "*\"the two function as daily attack powers for you\"* is a "
            "per-character usage reinterpretation that nothing can "
            "express. Half of it would be wrong in either direction: the "
            "powers without the usage swap are two free encounter attacks, "
            "and the swap without the powers reaches nothing."
        )
    )
    return row


# -- the nine rows with combat meaning ---------------------------------------


@power(
    "cf:wizard-bladesinger-f0",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("Weapon.as_wand",),
)
def bladesinger_blade(c: Cast) -> None:
    """The chosen blade is an implement.

    *"You gain proficiency with that weapon as an implement, meaning you
    can use your implement powers through it."* `c.as_implement` is exactly
    that and needed nothing built -- it is the commonest property in the
    magic weapon slot, 35 item blocks print it, and it writes a flag onto
    the weapon rather than holding an effect because the sentence is a fact
    about the object.

    **The choice is not modelled and does not need to be.** The card has
    the player pick one blade at creation; a character holds one main
    weapon, so "that weapon" and "the weapon in your hand" are the same
    thing in every fight. What is asked instead is that the thing in hand
    *is* a one-handed blade, which is the half that can be false.

    Dropped: *"the weapon also counts as a wand for you, although it can
    be enchanted only as a weapon."* `Gear.implement` picks a held weapon
    by group and `as_implement` makes this one eligible, but "counts as a
    **wand**" is narrower -- it is what a wand-only implement feat or item
    asks about -- and there is no field for a weapon's implement *kind*.
    The enchantment half is out of scope the way every `Level 11:` line is.
    """
    if _a_blade_in_one_hand(c):
        c.as_implement(on=c.me)


@power(
    "cf:wizard-bladesinger-f1",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_cantrips(c: Cast) -> None:
    """"You gain three cantrips of your choice."

    **The family IS in the tree and the page names it.** This carried
    `chargen.power_choice()` on two claims, and the second was the load
    bearing one: *"`Keyword.CANTRIP` does not exist, so even with the
    draw there would be nothing to draw from."* True about the keyword
    and false about the family -- the bladesinger's own class page
    prints the five cantrips under the sentence, exactly as the mage's
    page prints the same five under its own. A keyword was never needed;
    the list was printed all along.

    So this is an ordinary `chargen.BUILD_OPTIONS` fork with
    `OPTION_PICKS` of three, and the draw the marker asked for is the
    one every other fork already used. `#1268`.
    """
    for took in c.chosen_options("cf:wizard-bladesinger-f1"):
        c.grant_row(took, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:wizard-bladesinger-f3",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_spellbook(c: Cast) -> None:
    """The spellbook, and preparing out of it.

    The same row `cf:wizard-arcanist-f2` is, and written the same way
    deliberately: both chassis print the same mechanic, and the judgement
    in `controllers_sa.py` -- that preparing happens when the fight starts,
    because the engine has no extended rest and arming a trait is the only
    hook there is -- applies unchanged. One daily and one utility out of
    the book into a slot standing empty.

    **It does not swap a prepared power for an equivalent one.** The slot
    count never changes, so a swap has to prefer one row over another and
    nothing here can; re-preparing every fight would be churn dressed as a
    feature.

    The printed sentence about not preparing after a rest -- *"you retain
    the powers you previously prepared"* -- is what the engine does by
    construction, since nothing takes a prepared power away.
    """
    book = c.spellbook()
    known = c.world.get(c.me, Powers)
    if not book or known is None:
        return
    for slot in (Usage.DAILY, Usage.ENCOUNTER):
        options = [ref for ref in book
                   if (p := get(ref)) is not None and p.usage is slot]
        prepared = [ref for ref in known.known
                    if (p := get(ref)) is not None
                    and p.usage is slot and p.level > 0]
        if not options or prepared:
            continue
        pick = c.choose(options, f"{c.ref}: which {slot.value} to prepare")
        if pick is not None:
            c.prepare(pick)


@power(
    "cf:wizard-bladesinger-f4",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_song(c: Cast) -> None:
    """"You gain the p14285 power."

    A no-op grant: `p14285` is declared `cls="wizard"` at level 0, so
    `chargen.loadout` has already dealt it and `c.grant_row` returns
    `None`. Written out because it is the row three features below gate
    on, and a reader following those needs to land somewhere. `#1259`.
    """
    c.grant_row(SONG, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:wizard-bladesinger-f5",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("chargen.power_choice(keyword=)",),
)
def bladesinger_bladespells(c: Cast) -> None:
    """"You gain three wizard at-will attack powers that have the bladespell
    keyword."

    **This one is load-bearing and the others of its kind are not.** All
    six bladespells are written -- `p14286` through `p14291`, every one
    firing -- and `Keyword.BLADESPELL` exists, so unlike the cantrips there
    is a real family to draw from. What is missing is the draw: `loadout`
    deals a class's at-wills from the whole class pool, so a bladesinger
    gets whatever the wizard's at-wills are and the six rows its own two
    later features are *about* may not be among them.

    A different symbol from `-f1`'s for that reason. The gap there is "a
    draw from a family"; the gap here is "a draw **narrowed by keyword**",
    and the keyword is the thing that exists. One marker naming one gap --
    a shared symbol would report both ready the day either landed.
    """


@power(
    "cf:wizard-bladesinger-f6",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_grace(c: Cast) -> None:
    """Two clauses with two different requirements, which is why they are
    asked separately.

    *"Your ranged attacks and area attacks do not provoke opportunity
    attacks while you are holding a one-handed melee weapon."* The
    requirement is only the weapon -- the other hand may hold anything --
    so this half asks neither `_sword_hand` nor the blade test.
    `c.no_provoke(when=)` gates on the row being rolled, which is where
    `reach.kind` lives.

    *"In addition, you gain a +2 **shield** bonus to AC while you are
    wearing light armor or no armor and are holding a one-handed melee
    weapon in one hand and no weapon or shield in the other."* That is
    `_sword_hand` plus the armour, and `kind="shield"` rather than untyped
    because the card prints the word -- which matters: a bladesinger who
    somehow carries a shield gets one bonus, not two.

    The armour is read once when the trait arms, as every standing armour
    gate in this tree is; the weapon is read live in both clauses, because
    `_sword_hand` is a `(world, eid)` question and a free hand is the thing
    a fight changes.
    """
    me = c.me
    gear = c.world.get(me, Gear)
    held = gear.main if gear is not None else None
    if held is not None and not held.ranged and not held.two_handed:
        c.no_provoke(on=me, until=When.ENCOUNTER, when=_a_ranged_or_area_row)
    if gear is not None and gear.armour not in UNARMOURED:
        return
    if _sword_hand(c.world, me):
        c.bonus(AC, 2, on=me, until=When.ENCOUNTER, kind="shield")


@power(
    "cf:wizard-bladesinger-f7",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_prowess(c: Cast) -> None:
    """"When you make a melee basic attack with a weapon you wield in one
    hand, you can use Intelligence instead of Strength for the attack roll
    and the damage roll."

    `c.rolls_with` is the whole of it, and one call pays both halves:
    `Attack.ability_for` reads the swap **before** the header and `mba`'s
    body reads `c.attack_mod`, so the attack roll and the damage roll both
    move. The same line `cf:bard-skald-f0` uses for Charisma, which is the
    second row in the tree to want it and the reason it is a verb.

    The gate is `(world, eid)` and asks what is in hand live, so a
    two-hander taken up mid-fight takes the swap away -- which is the
    printed "with a weapon you wield in one hand" and not an
    approximation of it.
    """
    c.rolls_with("mba", Ability.INT, on=c.me, until=When.ENCOUNTER,
                 when=lambda world, eid: _one_handed_swing(world, eid))


@power(
    "cf:wizard-bladesinger-f8",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_ritual(c: Cast) -> None:
    """"You gain the p463 power."

    A no-op grant of the same kind as `-f4`: `p463` is a level-1 wizard
    at-will, so a bladesinger of 1st level or higher has been dealt it.
    """
    c.grant_row("p463", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:wizard-bladesinger-f10",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_flourish(c: Cast) -> None:
    """"When you use a bladesinger daily attack power on your turn, you can
    make a melee basic attack as a minor action."

    A watch on `PowerResolved`, not on the attack being declared: the
    printed "when you use" is satisfied by the power having gone off, and
    reading the declaration would let the free swing happen before the
    power it is paid for.

    **"A bladesinger daily attack power" is read as the chassis's own**,
    which `-f2` and its six siblings are what would supply -- and they are
    the rows carrying `chargen.spellbook(encounter_as_daily=)`. So the test
    is a wizard daily attack power, since every daily attack a bladesinger
    holds is one: the chassis prints no daily attacks of its own and the
    seven rows that would reinterpret encounter powers into dailies have no
    writer. Narrowing further would be guessing at a list the chassis does
    not have.

    *"As a minor action"* is `c.extra_action(MINOR)`, which returns False
    when the creature has no minor left -- so the swing is offered at the
    printed price rather than for free, and declining is an answer because
    the card says *can*.
    """
    me = c.me

    def flourish(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me or c.world.turn != me:
            return
        used = get(getattr(ev, "power", "") or "")
        if used is None or used.cls != "wizard":
            return
        if used.usage is not Usage.DAILY or not used.is_attack:
            return
        reachable = [foe for foe in c.enemies() if c.adjacent(foe)]
        if not reachable or not c.extra_action(ActionType.MINOR, on=me):
            return
        victim = c.choose(reachable, f"{c.ref}: who to swing at", optional=True)
        if victim is not None:
            c.basic(on=victim)

    c.watch(PowerResolved, flourish, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:wizard-bladesinger-f13",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bladesinger_riposte(c: Cast) -> None:
    """"When an adjacent enemy hits you while your p14285 is active, you can
    make a melee basic attack against that enemy as an opportunity action."

    `c.arm_trigger` rather than `c.watch`, and that is the clause's whole
    second half: the verb is *"a `c.watch` that costs the watcher the
    action a trigger costs"*, so `cost=ActionType.OPPORTUNITY` charges the
    opportunity action the card charges. A bare watch would hand a
    bladesinger a free swing every time anything hit it.

    **`p14285` is read when the enemy hits, not when the trait
    arms**, which is the point of gating inside the handler. `p14285` is a
    minor-action power with an end-of-next-turn clock, so a bladesinger has
    not sung at the top of the fight and measuring there would switch the
    riposte off for the whole encounter.

    Reading it at all needs `p14285`'s bare labelled hold -- the five
    bonuses it lays are `p14285 attack+2` and friends, and
    `c.lingers_label` matches a label exactly, so none of them answers.
    That hold was added with this row.
    """
    me = c.me

    def hit_me(ev: Hit) -> bool:
        return (ev.target == me and ev.attacker != me
                and c.adjacent(ev.attacker) and c.lingers_label(SONG, on=me))

    def riposte(ev: Hit) -> None:
        c.basic(on=ev.attacker)

    c.arm_trigger(Hit, riposte, when=hit_me, cost=ActionType.OPPORTUNITY,
                  until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:wizard-bladesinger-f16",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("triggers.widen(Miss)",),
)
def bladesinger_unerring(c: Cast) -> None:
    """"When you make a melee basic attack while your p14285 is active, you
    can use a bladespell power even if the attack misses."

    What this needs is a **trigger widened from outside the rows it
    governs**. All six bladespells declare `on=BLADESPELL`, which is
    `Trigger(Hit, _bladespell, ...)` -- keyed on `Hit`, because hitting is
    what the printed bladespell asks for. This feature relaxes that to
    hit-or-miss for one character, so neither of the two doors fits:
    migrating the clause into the six bodies (`#550`'s arrangement) cannot
    help, because the bodies never run on a miss; and a `requires=` cannot
    add an event to a trigger that is already declared.

    `c.pre_empt`/`c.instead_of` is the documented exception for a feature
    naming a *class* of powers, and this is one -- but those replace what a
    power does, where this changes **when** it may be used.

    So one symbol, and it names the facility rather than the row: a
    declared `Trigger` that a standing effect can add an event arm to. The
    `p14285` gate above is already written and proved, so the day that
    lands this row is three lines.
    """


@power(
    "cf:wizard-bladesinger-f21",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("c.widen_to_adjacent(per_day=)",),
)
def bladesinger_whirl(c: Cast) -> None:
    """"Once per day when you use a bladespell power against an adjacent
    enemy, you can use that power against each adjacent enemy."

    A target widening with a daily hold, and neither half has a writer.
    The widening is not `c.aura` or a burst: the printed line keeps the
    power's own effect and repeats it per adjacent enemy, which is a
    different thing from a power that happens to hit several -- a
    bladespell's Effect lines fire once per target and some of them are
    about the triggering enemy specifically.

    `c.once_per_board` is the wrong clock: *"once per day"* spans the
    encounters between extended rests and that verb keys on the `World`,
    which is one fight. `Powers.per_day` counts per ref and this hold is
    not a power's.

    One symbol for both, because they are one printed sentence and a row
    that paid the widening without the limit would give a bladesinger the
    effect every round -- strictly stronger than print, which is the wrong
    direction to land half of.
    """


# -- the twelve spellbook rows -----------------------------------------------
#
# Each names its own printed level and its own kind. Grouped by kind rather
# than by level so a reader comparing the two markers has them side by
# side: the utilities are finished and the encounter-as-daily rows are one
# gap seven times.

bladesinger_book_9 = _spellbook_slots(
    "cf:wizard-bladesinger-f9",
    "of your level or lower", "utility")
bladesinger_book_12 = _spellbook_slots(
    "cf:wizard-bladesinger-f12",
    "of your level or lower", "utility")
bladesinger_book_15 = _spellbook_slots(
    "cf:wizard-bladesinger-f15",
    "of your level or lower", "utility")
bladesinger_book_18 = _spellbook_slots(
    "cf:wizard-bladesinger-f18",
    "of your level or lower", "utility")
bladesinger_book_20 = _spellbook_slots(
    "cf:wizard-bladesinger-f20",
    "of your level or lower", "utility")

bladesinger_book_2 = _spellbook_slots("cf:wizard-bladesinger-f2", "1st level", "encounter")
bladesinger_book_11 = _spellbook_slots(
    "cf:wizard-bladesinger-f11",
    "of 3rd level or lower", "encounter")
bladesinger_book_14 = _spellbook_slots(
    "cf:wizard-bladesinger-f14",
    "of 7th level or lower", "encounter")
bladesinger_book_17 = _spellbook_slots(
    "cf:wizard-bladesinger-f17",
    "of 13th level or lower", "encounter")
bladesinger_book_19 = _spellbook_slots(
    "cf:wizard-bladesinger-f19",
    "of 17th level or lower", "encounter")
bladesinger_book_22 = _spellbook_slots(
    "cf:wizard-bladesinger-f22",
    "of 23rd level or lower", "encounter")
bladesinger_book_23 = _spellbook_slots(
    "cf:wizard-bladesinger-f23",
    "of 27th level or lower", "encounter")
