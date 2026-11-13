"""The controller's features: the thing it channels its magic through.

A wizard's class page gives it four cantrips, a book, a bonus feat and one
choice that has any weight in a fight at all -- which implement it has
mastered. That choice is this file.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Keyword,
    SavingThrow,
    When,
    power,
)

#: How much harder the control leg makes one saving throw, as a raise an
#: item may change. `i1986p1` prints "increase your saving throw penalty by
#: 2", and the penalty is a local in the leg's own body -- so the leg reads
#: the raise rather than the item reaching in. A second, separate penalty
#: would be gated on nothing and would bite every save the creature made,
#: which is what that row's old docstring said made it unwritable. #715.
IMPOSITION_RAISE = "arcanist:imposition-raise"

#: The orb mastery's own card, which prints the same sentence this file's
#: control leg pays. See `orb_imposition`.
ORB_CARD = "cf:wizard-arcanist-f0c1"


def orb_imposition(c: Cast) -> bool:
    """*"Designate one creature you have cast a wizard spell upon that has
    an effect that lasts until the subject succeeds on a saving throw.
    That creature takes a penalty to its next saving throw against that
    effect equal to your Wisdom modifier."*

    **One body for two refs, because the compendium prints the sentence
    once and models it twice.** `cf:wizard-arcanist-f0`'s spec is the
    implement-mastery *chooser* -- *"choose one of the following forms:
    `-f0s1` ... `-f0s5`"* -- and `-f0s1` grants `ORB_CARD`, which is where
    the orb's two effects are printed. This file's `-f0` instead branches
    on the `control` and `war` legs and pays the clauses itself, which is
    the older reading and still live: `chargen.legs_for("wizard")` answers
    `('control', 'war')`.

    So both rows can reach this sentence on one character, and
    `i1986p1` -- which names `ORB_CARD` by ref, not `-f0` -- shows which of
    the two the compendium thinks owns it. The card does. `-f0` defers when
    the character holds it and pays otherwise, so a control-leg arcanist
    that never took the orb mastery is unaffected.

    Returns whether a penalty was laid, so a caller can tell a designation
    from a creature with nothing to designate.

    **The effect is designated, not merely the creature.** A wizard holding
    two save-ends effects on one target used to spend the penalty on
    whichever save came first, and a save against somebody else's effect
    spent it for nothing at all.

    *"Its **next** saving throw"*, which `once=True` cannot say: a one-shot
    modifier is spent by watching `AttackRolled`, so a save penalty written
    that way would be burned by the next attack anybody made and never by
    the save it is for. `Effects.save` reads the modifiers and *then*
    announces the throw, so ending the hold on `SavingThrow` spends it on
    the right one -- and `SavingThrow.against` is the effect rendered,
    which is what tells one of this creature's saves from another.
    """
    me = c.me
    victims = sorted(c.suffering())
    who = c.choose(victims, f"{c.ref}: who finds it harder to shake off") \
        if victims else None
    if who is None:
        return False
    held_by_target = [
        eff
        for eff in c.world.effects.of(who)
        if eff.source == me and eff.when is When.SAVE_ENDS
    ]
    if not held_by_target:
        return False
    against = c.choose(
        sorted(held_by_target, key=lambda eff: eff.id),
        f"{c.ref}: which effect it must shake off",
    )
    if against is None:
        return False

    def this_one(ctx: dict[str, Any]) -> bool:
        return ctx.get("effect") is against

    held = c.penalty(
        "save", c.wis_mod + c.amount_for(IMPOSITION_RAISE, 0),
        on=who, until=When.ENCOUNTER, when=this_one,
    )
    if held is None:
        return False
    label = str(against)

    def used(ev: SavingThrow) -> None:
        if ev.actor == who and ev.against == label:
            c.world.effects.end(held, "used")

    c.watch(SavingThrow, used, until=When.ENCOUNTER, on=who, label=c.ref)
    return True


@power(
    "cf:wizard-arcanist-f0",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def wizard_implement(c: Cast) -> None:
    """Once a fight, the implement does something the spell did not.

    Five forms are printed and `chargen.BUILDS["wizard"]` carries two legs.
    The two that *are* the legs are written: one leans on Wisdom and its own
    text says it is what the control build takes, the other leans on
    Dexterity and says it is what the war build takes. The remaining three
    are `cf:wizard-implement-rest` in `docs/blocked.json` -- one stores an
    unprepared power, one pays out on a summoning, one repeats a missed
    illusion, and none of the three forks on anything a `Build` records.
    Two of them do have a build section naming them on the class page, so
    the leg is writable the moment the mastery is.

    **Both legs are asked by name.** The second used to be the `else` of
    the first, so a wizard on any leg that was not the war one got the
    control mastery whether it had chosen it or not -- true today of two
    legs and untrue the moment a third is added.

    Both are printed free actions, not traits, so this is declared with the
    action a player spends rather than armed at the start of the fight.

    **No Requirement is declared.** Both halves print "you must wield an
    orb" / "a wand", and `chargen` gives a wizard no implement to hold at
    all -- `Gear.weapons` is empty for the class -- so a `requires=` gate
    would refuse the row forever rather than describing it. The mastery is
    the implement here. The orb half also prints "on your turn", which the
    free action's own cost already comes to for a row nothing triggers.

    The orb's second printed option -- extending an at-will effect that
    would end this turn into the next -- is not written: `Effects` clocks a
    duration off a `When`, and there is no way to push one effect's clock
    on by a turn without rewriting what it is.
    """
    if c.build("war"):
        # "A bonus to a single attack roll." Spent on the roll, which is
        # exactly the moment `once=True` ends an attack modifier.
        c.bonus("attack", c.dex_mod, until=When.EONT, on=c.me, once=True)
        return
    if not c.build("control"):
        return
    # **The card owns this clause when the character holds it.** `ORB_CARD`
    # prints the same sentence and `-f0s1` grants it, so a control-leg
    # arcanist that also took the orb mastery would otherwise pay the
    # penalty twice -- and `i1986p1`, which raises it, names the **card**
    # by ref rather than this row. `orb_imposition` has the whole argument.
    if c.feat(ORB_CARD):
        return
    orb_imposition(c)


@power(
    "cf:wizard-arcanist-f1",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def wizard_rituals(c: Cast) -> None:
    """A bonus feat that lets the wizard perform rituals, and nothing else.

    Deliberately inert, like the cleric's. Empty rather than a note: a trait
    is run at the start of every fight, and a line in the log would be
    announcing something that is not happening.
    """
