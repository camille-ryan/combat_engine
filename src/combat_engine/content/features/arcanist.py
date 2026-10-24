"""Class features: the wizard's implement, the cleric's channelled power, and
the two legs of the rogue's tactic that are not modifiers.

Almost everything here is a **sub-option** -- `cf:...-fNsM` is a build choice,
`cf:...-fNcM` is a power card printed inside the feature's section. The
parents live in `controllers.py`, `leaders.py` and `strikers.py`, and several
of them already implement a branch outright: where the parent does, the
sub-option ref is **not declared here at all**. Declaring it would deal the
same card twice, and for a modifier it is worse -- an untyped bonus stacks
with itself, so the double is a silently larger number rather than a visible
duplicate. The skipped refs are named in the report and in the docstrings
below, because the fault is in the extraction rather than in the row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    DamageType,
    Gear,
    Keyword,
    Trigger,
    When,
    World,
    by_me,
    power,
    targets_me,
)
from combat_engine.engine.cast import MANOEUVRE_GRANTED_ATTACK
from combat_engine.engine.components import Companion, Weapon
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared, Hit, Miss, Summoned
from combat_engine.engine.query import distance_between

# -- the cleric ------------------------------------------------------------


@power(
    "cf:cleric-templar-f0",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def cleric_channel(c: Cast) -> None:
    """The permission to channel, and the budget that limits it.

    Deliberately inert, and unusually so: this feature *does* have a combat
    consequence, but not one that lives on a row. Its whole printed content
    is "once per encounter, and only one such ability per encounter" -- a
    shared allowance across a set of rows in four files, which is the
    `group=CHANNEL_DIVINITY` header field and `dsl._group_spent` enforcing
    it. Nothing is left for a body to do: the rows that spend the budget
    already carry it, and a second copy laid here would be a second
    allowance rather than the same one.

    Empty rather than a note, for the reason `cf:cleric-templar-f3` is: a
    trait runs at the start of every fight and a line in the log would be
    announcing a thing that is not happening.
    """


@power(
    "cf:cleric-templar-f2",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def cleric_word(c: Cast) -> None:
    """The feature's whole printed benefit is that you have the row.

    It names `p1455` outright and that row is declared, so this grants it.
    `c.grant_row` returns None for a row the creature already knows, which
    is the ordinary case for a cleric off `chargen.loadout` -- the feature
    is why it is on the sheet, and granting it again is not a second copy.

    The card reprinted beside this feature as `cf:cleric-templar-f2c0` is
    the same printed block as `p1455` and is **not** declared: two rows
    would be two encounter allowances for one printed power.
    """
    c.grant_row("p1455")


# -- the rogue's tactic ----------------------------------------------------
#
# Four legs are printed. `cf:rogue-scoundrel-f1` in `strikers.py` already
# implements two of them -- the Charisma one as a gated AC bonus and the
# Strength one as a bonus on the extra damage -- so `cf:rogue-scoundrel-f1s0`
# and `cf:rogue-scoundrel-f1s1` are not declared. Both would be untyped
# bonuses laid a second time on a chassis that already has them.
#
# The other two the parent's own docstring sets aside as "rows of their own
# on the legs that name them", and those legs now have refs. They are here.


@power(
    "cf:rogue-scoundrel-f1s2",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.stealth_speed()", "c.hide(cover=)"),
)
def rogue_tactic_cunning(c: Cast) -> None:
    """Both printed halves are about when a Stealth check may be made.

    The first is the movement penalty -- none for moving more than two
    squares, half of it for running -- and `engine/skills.py` has no speed
    term in a Stealth check to reduce. The second is permission to attempt
    a hide on ordinary cover or concealment after moving three squares,
    where `c.hide` takes no cover argument and grants the hidden state
    outright. Granting it on a `MoveEnd` would hide the rogue rather than
    let it try, which is strictly stronger than the card.
    """


_CLUBS = ("w3593", "w3596")


def _weapon_swung(world: World, eid: int, ctx: dict[str, Any]) -> Weapon | None:
    """Which weapon a weapon attack is being swung with, if it is one.

    The damage context carries a power ref and no weapon, so the grip is
    reconstructed the way `c.w` chooses it: the ranged weapon on a ranged
    branch, the main hand otherwise.
    """
    declared = get(ctx.get("power") or "")
    if declared is None or Keyword.WEAPON not in declared.keywords:
        return None
    gear = world.get(eid, Gear)
    if gear is None:
        return None
    if ctx.get("ranged") and gear.ranged is not None:
        return gear.ranged
    return gear.main


@power(
    "cf:rogue-scoundrel-f1s3",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    # **The proficiency is a header column and both weapons are printed ones.**
    # `chargen.proficiency` reads this and hands the arms over at build time, which
    # is the only moment the clause can happen in -- `f2783` is the same shape. The
    # marker named it as missing and it had arrived.
    proficiency=("w3593", "w3596"),
)
def rogue_tactic_bludgeon(c: Cast) -> None:
    """Three clauses; two land and the middle one does not.

    The proficiency is a chargen column rather than a modifier, and it is declared
    in the header now -- `chargen.proficiency` reads `proficiency=` and hands the
    club and the mace over when the character is built, which is the only moment
    "you are proficient with" can happen in.

    "You can use those weapons with the extra damage or any rogue power that
    normally requires a light blade" is a weapon counting as a group it is not in,
    which the requirement gates ask of `Gear` directly and nothing can rewrite.

    What is left is the rattling rider, and it is written: a club or a mace
    delivering an attack with that keyword adds the Strength modifier to
    the damage roll. Gated on the weapon actually swung rather than
    installed on the strength of what was in hand when the fight began, and
    on the power's own keyword, which the damage context's `power` ref
    reaches.
    """
    me = c.me
    # One waiver, not two: a club and a mace are both group `mace`, so
    # naming the group covers the pair the card names.
    c.counts_as("light blade", holding="mace")

    def bludgeoning_and_rattling(ctx: dict[str, Any]) -> bool:
        declared = get(ctx.get("power") or "")
        if declared is None or Keyword.RATTLING not in declared.keywords:
            return False
        weapon = _weapon_swung(c.world, me, ctx)
        return weapon is not None and weapon.ref in _CLUBS

    c.bonus(
        "damage", c.str_mod, until=When.ENCOUNTER, on=me,
        when=bludgeoning_and_rattling,
    )


# -- the wizard's implement ------------------------------------------------
#
# Five masteries are printed. `cf:wizard-arcanist-f0` in `controllers.py`
# implements two of them by build -- the orb that penalises a save and the
# wand that raises one attack roll -- so four refs are **not** declared:
# the two cards `cf:wizard-arcanist-f0c1` and `cf:wizard-arcanist-f0c3`, and
# the two legs that are those same two branches, `cf:wizard-arcanist-f0s1`
# and `cf:wizard-arcanist-f0s5`.
#
# The remaining three masteries the parent sets aside outright, and they are
# what this section is: the orb that repeats a missed illusion, the staff,
# and the two tomes.
#
# No Requirement is declared on any of them. Every card prints "you must
# wield an orb" or "a staff" or "a tome", and `chargen` gives a wizard no
# implement to hold at all -- `Gear.weapons` is empty for the class -- so a
# `requires=` gate would refuse the row forever rather than describe it. The
# mastery is the implement here, which is the reading the parent takes.


@power(
    "cf:wizard-arcanist-f0c0",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    trigger="you miss an enemy with a wizard illusion power",
    on=Trigger(Miss, by_me, "you miss an enemy with a wizard illusion power"),
)
def wizard_orb_deception(c: Cast) -> None:
    """The missed spell is thrown again at somebody standing nearby.

    "Repeat the attack" is `c.grant_attack(reentrant=True)` aimed back at
    the caster: the swing is the very row and the very use being answered,
    so the in-flight guard and the usage limit both have to stand aside for
    it, and that is exactly what the flag is for.

    **"The chosen enemy cannot also be a target of the original attack"
    plays now.** It was marked `Miss.all_targets`, which names no field --
    and the answer was already on the event: `among` carries the whole
    target list of the one power use, set on every attack event by
    `resolve`, and `triggers.leaves_me_out` had been reading it for the
    same reason. Excluding only `ev.target` offered the other two creatures
    of a three-target burst straight back as fresh ones.
    """
    ev = c.trigger
    if ev is None:
        return
    spell = get(ev.power)
    if spell is None or spell.cls != "wizard" or Keyword.ILLUSION not in spell.keywords:
        return
    struck = set(getattr(ev, "among", ()) or (ev.target,))
    nearby = sorted(e for e in c.within(3, of=ev.target, side="enemy") if e not in struck)
    if not nearby:
        return
    who = c.choose(nearby, "cf:wizard-arcanist-f0c0: who the spell finds instead")
    if who is None:
        return
    c.grant_attack(c.me, on=who, ref=ev.power, attack_bonus=c.cha_mod, reentrant=True)


#: How much the staff form adds to the attacked defence, as a raise an
#: item may change. `i2633x1` prints "increase the bonus to defense by an
#: amount equal to the enhancement bonus of this staff", and the number the
#: leg hands out is a local in its own body -- so the leg has to **read** a
#: raise rather than the item reaching into it. `f790` is the worked
#: example and `c.change_amount`'s own docstring is the rule: a raise on a
#: mechanic whose body still hard-codes its number is a modifier nothing
#: reads. #715.
STAFF_DEFENCE_RAISE = "arcanist:staff-defence-raise"


@power(
    "cf:wizard-arcanist-f0c2",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    trigger="an attack targets you",
    on=Trigger(AttackDeclared, targets_me, "an attack targets you"),
)
def wizard_staff_defense(c: Cast) -> None:
    """A Constitution modifier on whichever defence is being attacked.

    The defence is read off the event rather than fixed at AC: the card
    says "defense", and `AttackDeclared` carries the one the roll is
    against. Untyped -- the card prints no type word.

    "You can declare the bonus after the DM has already told you the damage
    total" is table procedure for a table that rolls before it asks. An
    interrupt resolves before the roll here, which comes to the same
    outcome; `once=True` spends the bonus on that one attack.
    """
    ev = c.trigger
    if ev is None:
        return
    # The printed number is the Constitution modifier; `STAFF_DEFENCE_RAISE`
    # is what an item adds to it. Read here rather than laid as a second
    # bonus from the item, because `PowerResolved` does not carry which
    # defence this picked -- so a second bonus would have to cover all four
    # and would be spent by whichever attack came next.
    c.bonus(
        ev.vs,
        c.con_mod + c.amount_for(STAFF_DEFENCE_RAISE, 0),
        until=When.EOT, on=c.me, once=True,
    )


@power(
    "cf:wizard-arcanist-f0s0",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def wizard_orb_mastery_deception(c: Cast) -> None:
    """The leg's whole benefit is the card beside it, once a fight.

    "Once per encounter" is the card's own `usage`, so the leg grants it
    and adds nothing: a second limit here would be a second budget.
    """
    c.grant_row("cf:wizard-arcanist-f0c0")


@power(
    "cf:wizard-arcanist-f0s2",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def wizard_staff_mastery(c: Cast) -> None:
    """The one leg that is worth something before it is used.

    A standing +1 to AC with no type word in front of it, so untyped, plus
    the card. The bonus is the implement's rather than the wizard's, but
    the engine has no implement to hang it on and the leg is the mastery
    here -- the same reading the parent takes for the Requirement.
    """
    c.bonus(AC, 1, until=When.ENCOUNTER, on=c.me)
    c.grant_row("cf:wizard-arcanist-f0c2")


@power(
    "cf:wizard-arcanist-f0s3",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def wizard_tome_mastery_binding(c: Cast) -> None:
    """Everything this summoning brings in hits harder.

    Declared as the free action the card prints, not a trait: it is spent
    before the summoning power and pays out on what that power puts on the
    board. So the body arms a watcher rather than raising anything now --
    `Summoned` is the event, and it is the only thing that names the
    creature that arrived.

    The watcher is **not** `once=True`: a power that brings in three
    creatures gives the bonus to all three, which is what "all creatures
    summoned by that power" says. It lapses at the end of this turn, which
    is as close as an event with no power ref on it gets to "that power" --
    a wizard has one standard action to summon with.

    Untyped: no type word is printed. The damage bonus itself lasts the
    fight, because the creature does.
    """
    me, extra = c.me, c.con_mod

    def arrived(ev: Summoned) -> None:
        if ev.actor == me:
            c.bonus("damage", extra, until=When.ENCOUNTER, on=ev.summon)

    c.watch(Summoned, arrived, until=When.EOT, on=me, label="cf:wizard-arcanist-f0s3")


@power(
    "cf:wizard-arcanist-f0s4",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def wizard_tome_mastery_readiness(c: Cast) -> None:
    """A power the wizard does not know, held ready and paid for in kind.

    **Written, and the note below it was already pointing at the answer.**
    It said `c.borrow_row(cls=, level=, usage=, attacks=)` is *"precisely
    'the card names a set and asks the character to take one of it'"* and
    then marked the row anyway, on the ground that *"there is nowhere to
    record a power that is stored rather than known."* `c.borrow_row` is
    that record: it hands the chosen row over through `c.grant_row`, with
    the printed once-per-encounter as `uses=1`, which is a power the
    character may use and does not know -- the fourth state the old note
    wanted.

    The price landed separately and is the other half: *"expending another
    unused wizard attack power of its level or higher"* is
    `c.unspent(cls="wizard", level=<floor>, usage=ENCOUNTER, attacks=True)`
    for the candidates and `c.expend_row` for the one chosen.
    `c.unspent`'s own docstring names this sentence -- *"'and expend an
    unused wizard attack power of an equal or higher level' is printed on
    three tomes"* -- and this is the fourth card with it, which was not in
    that count.

    **The shape is `items/implement_b._tome_trade`'s and so are its three
    traps**, which is why the loop is one walk rather than two statements:
    the ladder is walked downwards so the price's floor is *the rung the
    card was taken from* and not the character's level; the candidates are
    read **before** the borrow, because `c.borrow_row` grants a fresh
    wizard power of exactly the right class and level and a price read
    afterwards could pick the borrowed card and make the trade free; and
    nothing is charged on a rung with no card to lend.

    Hand-written rather than calling that helper: it lives in `items/` and
    hard-codes a tome's keyword narrowing, and this card names the whole
    class list instead.

    **Which power is stored is settled here rather than at character
    creation**, which is the call `c.borrow_row` already makes and states:
    *"inside one encounter a choice made at arming and a choice made at
    character creation are the same choice."* The printed "replace the
    stored power each time you gain an encounter power" is a between-fights
    clause and there is no persistence to hold it.

    `usage=ENCOUNTER` on both halves. The card as imported says "attack
    power", and the replace clause -- "each time you reach a level that
    lets you choose an **encounter** power" -- is what says which kind;
    a daily traded for a daily is not what the rest of the card describes.

    No Requirement, which is this file's standing convention for the
    mastery rows: the mastery *is* the implement. The comment that states
    it argues from *"`chargen` gives a wizard no implement to hold at all
    -- `Gear.weapons` is empty for the class"*, and that premise is stale
    -- a wizard is dealt an orb now -- but the conclusion holds, because
    an orb is not a tome and the gate would refuse the row forever.
    """
    for lvl in range(c.level, 0, -1):
        # Read before the borrow, so the borrowed card cannot pay for
        # itself -- `_tome_trade`'s second trap, in its own words.
        pool = c.unspent(
            cls="wizard", level=lvl, usage=ENCOUNTER, attacks=True,
        )
        if not pool:
            continue
        taken = c.borrow_row(
            cls="wizard", level=lvl, usage=ENCOUNTER, attacks=True, uses=1,
        )
        if not taken:
            continue
        pick = c.choose(pool, c.ref)
        if pick:
            c.expend_row(pick)
        return


@power(
    "cf:wizard-arcanist-f3",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def wizard_cantrips(c: Cast) -> None:
    """Four cantrips, and every one of them is narrative.

    Deliberately inert rather than unwritten, like the rituals feature
    beside it: `content/powers/wizard/level_0.py` declares all four the
    same way, because lighting a lamp and moving a coin have no combat
    consequence to invent. The cantrips are rows of their own; this feature
    is only the line saying the wizard has them.
    """


# -- the other wizard page -------------------------------------------------


_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


@power(
    "cf:wizard-sha-ir-f0",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
)
def shair_element(c: Cast) -> None:
    """Standing next to the familiar is worth a resistance, for everybody.

    The element is chosen at the start of the fight rather than at the end
    of an extended rest: the rest is where the card puts the choice, and
    the engine has no rest -- a fight is the first moment the choice can be
    made and the last moment it matters.

    **Gated rather than flat.** `Defences.resist` is a number per type with
    nowhere to hang "while adjacent to the familiar", so a flat one would
    shrug off the element everywhere on the board. The gated form is a
    modifier, and `resolve.damage` reads it after the flat one.

    Adjacency and the mode are asked **inside** the gate, not at arm time:
    both change every turn, and a familiar that has gone passive has no
    square at all, which is what makes it not-adjacent rather than nowhere.

    The 21st-level doubling is out of scope; the project stops at 10.
    """
    element = c.choose(list(_ELEMENTS), "cf:wizard-sha-ir-f0: which element")
    if element is None:
        return
    me, amount = c.me, c.con_mod

    def beside_the_familiar(who: int) -> Any:
        def gate(ctx: dict[str, Any]) -> bool:
            pet = c.familiar(of=me)
            if pet is None:
                return False
            kept = c.world.get(pet, Companion)
            if kept is None or kept.passive:
                return False
            return c.adjacent_to(pet, who)

        return gate

    for friend in [me, *c.allies()]:
        c.resist(
            amount, element, until=When.ENCOUNTER, on=friend,
            when=beside_the_familiar(friend),
        )


@power(
    "cf:wizard-sha-ir-f1",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def shair_familiar(c: Cast) -> None:
    """A familiar. The bonus feat that says so is written but not landed.

    A dozen wizard rows open with `pet = c.familiar()` and return when
    there is none, and nothing in the tree has ever put one on the board --
    this is the feature that says a character has one, so it calls it.
    `c.call_companion` relocates rather than accumulates, so arming the
    trait twice is still one familiar.

    **The bonus feat is granted now, and the old note's premise is
    false twice over.** It said the spec prints no id: the spec prints
    `f738`, which is #628/#340's ETL residual repaired -- and `f738` is a
    declared row. And it said the only thing the feat does is already
    written above, which is the half that is true of its *first* sentence
    and not of its second: `f738` also carries the familiar-feat chain's
    defence rider, and that rider never armed for a sha'ir because the
    character did not hold the row that lays it.

    `c.grant_row` is what hands it over, and its own docstring settles the
    ordering worry: `turns.arm_traits_of` re-reads between passes, so a
    trait granted during arming is armed. **After `c.call_companion`**,
    because `f738`'s body reads `c.familiar()` and lays its bonus on the
    creature it finds -- granted first, the rider would land on nobody.

    **It moves all seven replay fixtures, and it moves them by insertion
    only.** Measured against the recorded logs with effect ids and event
    references normalised out, which is the comparison that decides it:

        every fixture   +4 events, 0 removed, party byte-identical
        level-3-full    +6, because `f1288` inserts two of its own

    The four are the grant's `EffectApplied`, `f738` arming
    (`PowerUsed`/`PowerResolved`, `rolls=[]`), and its expiry. **No
    `AttackRolled`, `DamageRolled`, `DamageApplied` or `SavingThrow` figure
    moves in any of the seven**, and nothing present in a recorded log is
    absent from the new one.

    A first pass read this as the dice moving in five of the seven and held
    the grant back for it. That was a measurement artefact: the diff
    normalised `effect=\\d+` but **not** the effect ids printed inside a
    label (`e74[...]` -> `e75[...]`) or the event references a trigger
    carries (`Miss#338` -> `Miss#339`), both of which the inserted event
    bumps by one for the whole rest of the log. Those re-numberings aligned
    as `replace` blocks and every figure inside them was identical.
    Comparing the event *multisets* under the right normalisation is what
    tells a renumbering from a real move; a line-diff cannot.

    `replay._drawn`'s "**under which a real regression could ride in
    unseen**" is satisfied rather than waived: an insertion-only re-record
    with an identical party is the case it was written to permit.

    `c.grant_row` goes **immediately below `c.call_companion`** -- the order
    matters, since `f738`'s body reads `c.familiar()` and lays its bonus on
    the creature it finds, and granted first the rider lands on nobody.

    What is *not* a clause this row is missing: "which familiar" is a species
    the engine does not model, and the power replacement is an extended-rest
    action with no combat consequence.
    """
    c.call_companion(kind="familiar", speed=6)
    c.grant_row("f738")


@power(
    "cf:wizard-sha-ir-f2",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def shair_cantrips(c: Cast) -> None:
    """Four cantrips again, on the other page, and inert for the same reason."""


# --------------------------------------------------------------------------
# The mage's school tiers, `cf:wizard-mage-f4sN`
#
# Eighteen sub-options over three tiers, imported by #584 and #586 -- the
# class had never had a single feature read, so none of these refs existed
# until then. This is the middle tier, and the only one of the three whose
# six benefits are all the same shape: two named skills, +2 each, no type
# word in front of the number.
#
# **Hand-written one by one rather than looped over a table**, which is the
# global rule and earns its keep here: the six pairs overlap but no two are
# the same pair, and a table would hide that `f4s0` and `f4s5` share one
# skill and differ in the other.
#
# `until=When.ENCOUNTER` and no `kind=`, which is what
# `cf:wizard-arcanist-f0s2` does for its standing bonus and for the same two
# reasons: a class feature is re-armed every fight, and the card prints no
# word before "bonus", so the bonus is untyped.
#
# The schools these belong to are printed names and are in `localization/`;
# the ref is what says which. #581.
# --------------------------------------------------------------------------


def _expert(ref: str, first: str, second: str, level: int):  # noqa: ANN202
    """Two skills, +2 each -- the whole of one middle-tier benefit.

    The one helper the global rule allows, for a run of rows that genuinely
    share a shape. It takes the two skill names rather than deriving them,
    so each row below still says its own pair out loud.

    **`level` is a parameter because it was a bug as a constant.** This read
    `level=4` on all six rows, and the page prints `Level 5:` nine
    characters before the heading these come under. The 4 was the feature's
    `ord` -- its index among the class's features -- which is exactly the
    "never derive a number the page prints" rule: `cf:wizard-mage-f4` is the
    fifth feature, not a fifth-level one, and the two agree nowhere else
    either -- `cf:wizard-mage-f0` is level 1 and `cf:wizard-mage-f6` is
    level 10.

    The same tier is printed twice, at two levels, for the first and second
    school a character took -- `f4sN` at 5 and `f5sN` at 8 -- so the level
    cannot be a property of the shape at all.
    """

    @power(
        ref,
        level=level,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        c.bonus(f"skill:{first}", 2, until=When.ENCOUNTER, on=c.me)
        c.bonus(f"skill:{second}", 2, until=When.ENCOUNTER, on=c.me)

    slot = ref.rsplit("-", 1)[-1]
    row.__name__ = "mage_expert_" + slot
    # Which parent feature chose the school this benefit belongs to. `f4sN`
    # is the first school a character took, `f5sN` the second -- same six
    # benefits, same shape, a different choice and a different level.
    chose = "cf:wizard-mage-f0" if slot.startswith("f4") else "cf:wizard-mage-f3"
    row.__doc__ = (
        f"The middle tier of the school chosen for `{chose}`: "
        f"+2 to {first} and +2 to {second}.\n\n"
        f"    A skill bonus is a `skill:<name>` modifier, which is what the\n"
        f"    50 content files that lay one already write and what\n"
        f"    `engine/skills.py` reads beside the training `Skills` records."
    )
    return row


mage_expert_s0 = _expert("cf:wizard-mage-f4s0", "bluff", "diplomacy", 5)
mage_expert_s1 = _expert("cf:wizard-mage-f4s1", "endurance", "intimidate", 5)
mage_expert_s2 = _expert("cf:wizard-mage-f4s2", "bluff", "stealth", 5)
mage_expert_s3 = _expert("cf:wizard-mage-f4s3", "athletics", "endurance", 5)
mage_expert_s4 = _expert("cf:wizard-mage-f4s4", "intimidate", "stealth", 5)
mage_expert_s5 = _expert("cf:wizard-mage-f4s5", "bluff", "intimidate", 5)

# **The same tier again, for the second school, at level 8.** Three refs and
# not six: the compendium carries `f5s0`, `f5s1` and `f5s2` and no more,
# which matches `f3` -- the second-school Apprentice tier -- carrying three
# as well. So the pattern is the *page's*, not a truncation here, and the
# three it prints are the three written. If `f5s3`-`f5s5` ever appear in a
# rebuilt database, `symbols.py` will not notice and nothing else will
# either; `written.py` is what would.
#
# Each pays the identical benefit to its `f4sN` twin, because the card is the
# same card -- the only difference is which of the character's two schools it
# reads, and that choice is chargen's, not this row's.
mage_expert2_s0 = _expert("cf:wizard-mage-f5s0", "bluff", "diplomacy", 8)
mage_expert2_s1 = _expert("cf:wizard-mage-f5s1", "endurance", "intimidate", 8)
mage_expert2_s2 = _expert("cf:wizard-mage-f5s2", "bluff", "stealth", 8)


# --------------------------------------------------------------------------
# The mage's first school tier, `cf:wizard-mage-f0sN`
#
# Two of the six are written below. The other four want engine readers that
# do not exist and carry markers saying which -- they are not here, because a
# row is implemented before it is added or it carries a marker, and a marker
# on a row nobody has declared is not a thing. #581.
#
# Both of these rider on **the wizard's own hit with a power carrying the
# school's keyword**, which is only sayable since #589 recorded the schools
# and `7abc66e` put them in the headers a gate actually reads. The keyword
# comes off `get(ev.power)` -- the REGISTRY row -- which is the lesson from
# `f1836`: the database is not what a gate can see.
#
# `usage=AT_WILL, action=FREE` with a declared `on=`, the shape `rt:r18-t3`
# uses: the cards print no limit, so a limit here would be a budget the page
# does not have.
# --------------------------------------------------------------------------

_ILLUSION_HIT = "you hit a target with an arcane illusion power"
_NECROMANCY_HIT = "you hit at least one target with an arcane necromancy power"
_NETHERMANCY_HIT = "you hit a target with an arcane nethermancy power"


def _my_school_hit(word: Keyword):  # noqa: ANN202
    """My own hit with a power carrying this school's keyword."""

    def landed(world: World, me: int, ev: Hit) -> bool:
        if ev.attacker != me:
            return False
        row = get(ev.power)
        return bool(row and word in (row.keywords or ()))

    return landed


def _apprentice_illusion(ref: str, level: int):  # noqa: ANN202
    """One card, two refs: the illusion benefit at both levels it prints.

    `f0s2` is the school chosen at 1st level and `f3s2` the one chosen at
    4th, and the compendium prints the **same benefit text** under both --
    six of the mage's eighteen sub-options are printed twice this way. So
    this is the `_expert` arrangement rather than a copy: a second
    registration of one body, with the level the page gives each.

    A character cannot hold both, because `cf:wizard-mage-f3` prints
    "different from the one you chose at 1st level". Nothing here enforces
    that -- it is chargen's, and chargen does not model the second school
    at all yet, which is the half of #581 that is not content work.
    """

    @power(
        ref,
        level=level,
        cls="wizard",
        usage=AT_WILL,
        action=ActionType.FREE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        trigger=_ILLUSION_HIT,
        on=Trigger(Hit, _my_school_hit(Keyword.ILLUSION), _ILLUSION_HIT),
    )
    def row(c: Cast) -> None:
        _illusion_penalty(c)

    row.__name__ = "mage_apprentice_" + ref.rsplit("-", 1)[-1]
    row.__doc__ = _illusion_penalty.__doc__
    return row


def _my_school(word: Keyword):  # noqa: ANN202
    """A `when=` gate: is the row doing this one of my school's powers?

    Four rows had written this out by hand and the fifth would have been a
    fifth copy. The keyword comes off `get(ctx["power"])` -- the REGISTRY
    row -- and not off the database, which is `f1836`'s lesson: a gate
    cannot see the database.

    `ctx["power"]` is "the ref of the row doing this", the commonest gate
    key in the tree, so this needs no key of its own. The trigger-side
    counterpart is `_my_school_hit`, which asks the same question of an
    event rather than of a context.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        rolled = get(str(ctx.get("power", "")))
        if rolled is None:
            return False
        held = rolled.keywords or ()
        return Keyword.ARCANE in held and word in held

    return gate


def _illusion_penalty(c: Cast) -> None:
    """A -2 on the next swing the target takes **at the caster**, not on its
    next swing at anybody.

    `once=True` beside a `when=` gate is the whole of that, and it is right
    for a reason worth writing down because the comment on `Cast`'s
    once-keys reads the other way at a glance: it says a one-shot on
    `attack` is "spent by the attack roll", which would mean an attack on
    somebody else burns this penalty for free.

    It does not. Driven on a board: the hold survives the target attacking a
    bystander, whose target the gate rejects, and is spent by the attack on
    the caster. 160 rows in the tree already pair the two and all of them
    depend on that.

    The victim comes off `c.trigger` rather than `c.target`: this row has no
    target of its own, so a bare call would act on nobody.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    me = c.me
    c.penalty("attack", 2, on=victim, until=When.EONT, once=True,
              when=lambda ctx: ctx.get("target") == me)


mage_apprentice_s2 = _apprentice_illusion("cf:wizard-mage-f0s2", 1)
mage_apprentice_f3s2 = _apprentice_illusion("cf:wizard-mage-f3s2", 4)


@power(
    "cf:wizard-mage-f0s3",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger=_NECROMANCY_HIT,
    on=Trigger(Hit, _my_school_hit(Keyword.NECROMANCY), _NECROMANCY_HIT),
)
def mage_apprentice_s3(c: Cast) -> None:
    """Two temporary hit points for landing one.

    **"At least one target" needs no once-per-power guard**, which is the
    only subtle thing here. A burst that hits three creatures fires this
    three times, and `resolve.temp_hp` is explicit that temporary hit points
    do not stack -- the larger pool wins -- so three grants of 2 leave 2.
    The printed clause is satisfied by the engine's own rule rather than by
    a counter this row would otherwise have to keep.

    `on=c.me` because the gain is the caster's: the row has no target, so a
    bare call would grant them to nobody.
    """
    c.temp_hp(2, on=c.me)


@power(
    "cf:wizard-mage-f0s4",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger=_NETHERMANCY_HIT,
    on=Trigger(Hit, _my_school_hit(Keyword.NETHERMANCY), _NETHERMANCY_HIT),
)
def mage_apprentice_s4(c: Cast) -> None:
    """The creature struck sees distant enemies as half-hidden.

    **Written as the penalty concealment confers, not as concealment**, and
    the direction is why. `c.conceal(on=X)` grants it *to* X -- everything
    attacking X is -2 -- and this card does the opposite: the creature hit
    treats *other* creatures as concealed, so what moves is its own attack
    roll and only against targets more than 2 squares from it.

    Partial concealment is -2 to the attacker, which `c.conceal`'s own
    docstring states, so the number is the card's and not a guess. What is
    not modelled is concealment as a *state* -- a row asking "is that
    creature concealed" will not see this -- and no row in the tree asks
    that of a third party, which is why this is the faithful reading rather
    than a lossy one.

    The distance is measured at each attack rather than once: both
    creatures move.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    world = c.world

    def far_from_victim(ctx: dict[str, Any], who: int = victim) -> bool:
        aim = ctx.get("target")
        return (
            isinstance(aim, int)
            and aim != who
            and distance_between(world, who, aim) > 2
        )

    c.penalty("attack", 2, on=victim, until=When.EONT, when=far_from_victim)


@power(
    "cf:wizard-mage-f0s5",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_apprentice_s5(c: Cast) -> None:
    """Two standing clauses, and both verbs already existed.

    I had this marked as wanting a resistance-ignoring facility.
    `c.ignore_resistance(dtype=, when=)` has been there all along -- the
    same lesson the engine file states, that of roughly 21 verbs wanted
    across one issue 15 already existed.

    **And `vocab.py --find` did surface it; I called it wrong.** It takes
    `nargs="+"` and ANDs the words, so `--find ignore resistance` returns
    36 places with this verb at the top, while `--find "ignore resistance"`
    is one literal argument that cannot match the underscore in the name.
    It even prints "try one word, or a synonym" on an empty result, which
    is the line I skipped. Pass words, never a quoted phrase.

    **The two clauses are scoped differently and the card says so.** The
    damage bonus is "with arcane fire attacks", so it is gated on the power
    that is rolling; the resistance clause is "your attacks", unqualified,
    so it carries no gate at all. Writing the second with the first's gate
    would have been the tidier-looking mistake.

    The +2 at 11th level and +3 at 21st are paragon and epic, so they are
    out of scope rather than missing.
    """
    arcane_fire = _my_school(Keyword.FIRE)

    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=arcane_fire)
    c.ignore_resistance(dtype=DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


def _apprentice_forced(ref: str, level: int):  # noqa: ANN202
    """One card, two refs -- see `_apprentice_illusion` for why.

    The enchantment benefit, printed at 1st level for the first school and
    at 4th for the second.
    """

    @power(
        ref,
        level=level,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        _forced_squares(c)

    row.__name__ = "mage_apprentice_" + ref.rsplit("-", 1)[-1]
    row.__doc__ = _forced_squares.__doc__
    return row


def _forced_squares(c: Cast) -> None:
    """Two more squares of forced movement, on this caster's own powers.

    `c.extend_every` already lengthened every move of a *kind*; `c.shift`
    and `c.teleport` consulted it and the three forced-movement verbs did
    not, so a rider on a push had nowhere to land. Those three read it now.

    **The squares are the pusher's, not the pushed creature's**, which is
    the opposite of a shift and the whole reason the three readers are not
    copies of `c.shift`'s line. "When one of *your* powers allows you to
    pull, push, or slide a creature" is a rider the wizard carries and
    spends on somebody else's trip; reading the victim would have let a
    creature lengthen the pushes it suffers.

    Three calls rather than one because the card names three verbs and the
    engine keeps them apart -- a push and a slide differ in where the
    creature may end up, so one symbol over all three would be the kind of
    collapse `MANOEUVRE_BULL_RUSH_FOLLOW` exists to avoid.
    """
    arcane_enchantment = _my_school(Keyword.ENCHANTMENT)

    for kind in ("push", "pull", "slide"):
        c.extend_every(kind, 2, on=c.me, until=When.ENCOUNTER,
                       when=arcane_enchantment)


mage_apprentice_s0 = _apprentice_forced("cf:wizard-mage-f0s0", 1)
mage_apprentice_f3s0 = _apprentice_forced("cf:wizard-mage-f3s0", 4)


def _apprentice_reroll(ref: str, level: int):  # noqa: ANN202
    """One card, two refs -- see `_apprentice_illusion` for why.

    The evocation benefit, printed at 1st level for the first school and at
    4th for the second.
    """

    @power(
        ref,
        level=level,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        _reroll_one_one(c)

    row.__name__ = "mage_apprentice_" + ref.rsplit("-", 1)[-1]
    row.__doc__ = _reroll_one_one.__doc__
    return row


def _reroll_one_one(c: Cast) -> None:
    """**One** damage die showing a 1, rerolled **once**, on this school.

    `pick=1` and not the bare verb, and the difference is the whole reason
    the parameter exists. `c.reroll_ones()` is "reroll each die that shows a
    1 **until it shows a different number**" -- every low die, and never a 1
    afterwards. This card is "if any of the dice come up with a result of 1,
    **pick one of them**, reroll it, and use the new result": one die, and
    the new face stands even if it is another 1.

    Writing it with the bare verb would have shipped a strictly better
    feature than the page prints, on both counts at once, which is the
    mistake `f2360` is on record for. That is why this row sat unwritten
    rather than taking the nearest verb.

    `keyword=` rather than a `when=` gate because the verb already narrows
    that way and the card names exactly one school's keyword.
    """
    c.reroll_ones(
        pick=1, keyword=Keyword.EVOCATION, on=c.me, until=When.ENCOUNTER,
    )


mage_apprentice_s1 = _apprentice_reroll("cf:wizard-mage-f0s1", 1)
mage_apprentice_f3s1 = _apprentice_reroll("cf:wizard-mage-f3s1", 4)


# --------------------------------------------------------------------------
# The mage's top school tier, `cf:wizard-mage-f6sN`
#
# Four of the six. The two left want readers that do not exist: concealment
# asked of a third party as a *state* rather than as the penalty it confers
# (`f6s4`), and turning an attack's area into a zone after the fact
# (`f6s5`).
#
# **`f6s0` wanted neither of the things this comment used to claim.** It said
# "forces a creature to make an attack" needed a *moment* and that nothing
# announced it. Both halves were wrong, and reading `docs/symbols/` rather
# than guessing is what showed it: `PowerUsed` has carried `granted_by` and
# `granted_via` since the provenance work, `triggers.granted_by_me` and
# `triggers.granted_via()` are built on them, and `c.grant_attack` already
# had an `attack_bonus` channel. What was missing was one line -- the verb
# consulting a rider the granter carries, the same gap `c.extend_every` had
# for push, pull and slide. #581.
# --------------------------------------------------------------------------


@power(
    "cf:wizard-mage-f6s0",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_master_s0(c: Cast) -> None:
    """A +2 to the attack roll of a swing this caster's own school forced.

    A **rider on the granter**, not a clause in each forcing power. The card
    names a class of powers -- "one of your arcane enchantment powers" --
    which `content/CLAUDE.md` names as the one case that does not get
    written into the power it mentions, because there is no finite list of
    bodies to edit.

    So `c.grant_attack` reads `MANOEUVRE_GRANTED_ATTACK` off whoever is
    granting, and this lays it. The gate is `ctx["power"]` -- the row doing
    the forcing -- which is the commonest gate key in the tree and needed no
    addition.

    **The bonus is the granter's, read off the granter.** `c.grant_attack`
    deliberately asks `self.me` rather than the creature swinging: reading
    the swinger would let a creature improve the attacks it is *forced* to
    make, which is the mirror of the mistake `_extra_every` records for
    pushes and the reason `cf:wizard-mage-f0s0`'s squares belong to the
    pusher.

    `kind="power"` is not written here because `c.grant_attack` lays the
    modifier and already types it that way, which is what the card prints.
    """
    c.change_amount(
        MANOEUVRE_GRANTED_ATTACK, 2, on=c.me, until=When.ENCOUNTER,
        when=_my_school(Keyword.ENCHANTMENT),
    )


@power(
    "cf:wizard-mage-f6s1",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_master_s1(c: Cast) -> None:
    """Resistance to whatever this power deals, ignored; immunity, not.

    **`dtype=None` is the card rather than a shortcut.** The printed line is
    "a target's resistance to any of *those* types of damage" -- the types
    the power in hand deals -- and a power deals only its own types, so
    "ignore all resistance on this power's damage" is the same set by
    construction. Naming a type here would have been narrower than the card
    on every power that deals two.

    "You do not ignore any immunities" is `immunity=False`, which is the
    default and is stated here because it is the half a reader would check.
    """
    arcane_evocation = _my_school(Keyword.EVOCATION)

    c.ignore_resistance(
        on=c.me, until=When.ENCOUNTER, immunity=False, when=arcane_evocation
    )


@power(
    "cf:wizard-mage-f6s2",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_master_s2(c: Cast) -> None:
    """"Hit **or miss**", which is why this is two watchers and not a
    trigger.

    A row holds one declared `on=`, and this card fires on either outcome of
    the same attack -- so the trait lays a watcher on each, the way
    `cf:shaman-f0s1` lays one on `Healed`. Writing it as a `Hit` trigger
    would have been the quiet half-row: every miss doing nothing, and the
    audit no wiser because the hits work.

    `to="team"` rather than a word for "anybody". The card says "the next
    attack made against it" and `c.grants_advantage` recognises `me`, `ally`,
    `team` or one creature -- an unknown word is an error there, by design.
    `team` is the caster and the caster's allies, which is every attacker
    this engine can pose against an enemy.
    """
    def opened(ev: Hit | Miss) -> None:
        if ev.attacker != c.me:
            return
        rolled = get(str(getattr(ev, "power", "")))
        held = rolled.keywords if rolled is not None else ()
        if Keyword.ILLUSION not in (held or ()):
            return
        c.grants_advantage(on=ev.target, to="team", until=When.EONT, once=True)

    for moment in (Hit, Miss):
        c.watch(moment, opened, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "cf:wizard-mage-f6s3",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_master_s3(c: Cast) -> None:
    """One damage type, named, on one school's attack powers."""
    arcane_necromancy = _my_school(Keyword.NECROMANCY)

    c.ignore_resistance(
        dtype=DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=arcane_necromancy,
    )
