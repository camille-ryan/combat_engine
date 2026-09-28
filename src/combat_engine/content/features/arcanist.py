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
from combat_engine.engine.components import Companion, Weapon
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared, Miss, Summoned

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


_CLUBS = ("w:club", "w:mace")


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
    dropped=("chargen.proficiency()", "c.counts_as(group=)"),
)
def rogue_tactic_bludgeon(c: Cast) -> None:
    """Three clauses, and only the last is a number the engine can carry.

    The proficiency is a chargen column, not a modifier. "You can use those
    weapons with the extra damage or any rogue power that normally requires
    a light blade" is a weapon counting as a group it is not in, which the
    requirement gates ask of `Gear` directly and nothing can rewrite.

    What is left is the rattling rider, and it is written: a club or a mace
    delivering an attack with that keyword adds the Strength modifier to
    the damage roll. Gated on the weapon actually swung rather than
    installed on the strength of what was in hand when the fight began, and
    on the power's own keyword, which the damage context's `power` ref
    reaches.
    """
    me = c.me

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
    dropped=("Miss.all_targets",),
)
def wizard_orb_deception(c: Cast) -> None:
    """The missed spell is thrown again at somebody standing nearby.

    "Repeat the attack" is `c.grant_attack(reentrant=True)` aimed back at
    the caster: the swing is the very row and the very use being answered,
    so the in-flight guard and the usage limit both have to stand aside for
    it, and that is exactly what the flag is for.

    **"The chosen enemy cannot also be a target of the original attack" is
    dropped.** `Miss` is announced once per target and carries only this
    one, so a burst that missed three creatures offers the other two back
    as fresh targets. Only the creature this miss is about is excluded.
    """
    ev = c.trigger
    if ev is None:
        return
    spell = get(ev.power)
    if spell is None or spell.cls != "wizard" or Keyword.ILLUSION not in spell.keywords:
        return
    nearby = sorted(e for e in c.within(3, of=ev.target, side="enemy") if e != ev.target)
    if not nearby:
        return
    who = c.choose(nearby, "cf:wizard-arcanist-f0c0: who the spell finds instead")
    if who is None:
        return
    c.grant_attack(c.me, on=who, ref=ev.power, attack_bonus=c.cha_mod, reentrant=True)


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
    c.bonus(ev.vs, c.con_mod, until=When.EOT, on=c.me, once=True)


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
    todo=("c.stored_row()", "c.tome_powers()"),
)
def wizard_tome_mastery_readiness(c: Cast) -> None:
    """A power the wizard does not know, held ready and paid for in kind.

    Re-aimed off `c.expend_row()`: that verb exists now and spends a use
    of a row from outside it, which is exactly "expend another unused
    wizard encounter attack power" -- so the cost is writable and the
    row is still nothing without the rest. There is nowhere to record a
    power that is stored rather than known -- `Powers` holds known,
    prepared and expended, and a stored row is a fourth state the tome
    owns -- and nothing narrows a choice to the wizard's tome list.

    `c.prepare` is the near miss and it is the wrong tool: it swaps a row
    out of the spellbook for one that is in it, and the stored power is by
    definition one the wizard does not know.
    """


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
    dropped=("spec.feat_ref()",),
)
def shair_familiar(c: Cast) -> None:
    """The sha'ir has a familiar, which is the whole of it in a fight.

    A dozen wizard rows open with `pet = c.familiar()` and return when
    there is none, and nothing in the tree has ever put one on the board --
    this is the feature that says a character has one, so it calls it.
    `c.call_companion` relocates rather than accumulates, so arming the
    trait twice is still one familiar.

    **The bonus feat's ref is dropped.** The card names the feat in prose
    and the spec prints no id, so there is nothing for `c.feat` to be
    handed; what the feat *does* -- you have a familiar -- is written
    above, and the choice of which one is a species the engine does not
    model.

    The power replacement is an extended-rest action with no combat
    consequence, so it is not a clause this row is missing.
    """
    c.call_companion(kind="familiar", speed=6)


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
