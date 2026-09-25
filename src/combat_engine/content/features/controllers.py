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


@power(
    "cf:wizard-implement",
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
    are in `docs/blocked.json` -- one stores an unprepared power, one pays
    out on a summoning, one repeats a missed illusion, and none of the three
    forks on anything a `Build` records.

    Both are printed free actions, not traits, so this is declared with the
    action a player spends rather than armed at the start of the fight.

    **No Requirement is declared.** Both halves print "you must wield an
    orb" / "a wand", and `chargen` gives a wizard no implement to hold at
    all -- `Gear.weapons` is empty for the class -- so a `requires=` gate
    would refuse the row forever rather than describing it. The mastery is
    the implement here.
    """
    if c.build("war"):
        # "A bonus to a single attack roll." Spent on the roll, which is
        # exactly the moment `once=True` ends an attack modifier.
        c.bonus("attack", c.dex_mod, until=When.EONT, on=c.me, once=True)
        return

    # The other leg: somebody already carrying one of this wizard's
    # save-ends effects has a harder time shaking it off.
    me = c.me
    victims = sorted(c.suffering())
    who = c.choose(victims, "cf:wizard-implement: who finds it harder to shake off") \
        if victims else None
    if who is None:
        return

    def mine(ctx: dict[str, Any]) -> bool:
        return getattr(ctx.get("effect"), "source", None) == me

    held = c.penalty("save", c.wis_mod, on=who, until=When.ENCOUNTER, when=mine)
    if held is None:
        return

    # "Its **next** saving throw", which `once=True` cannot say: a one-shot
    # modifier is spent by watching `AttackRolled`, so a save penalty
    # written that way would be burned by the next attack anybody made and
    # never by the save it is for. `Effects.save` reads the modifiers and
    # then announces the throw, so ending it here spends it on the right one.
    def used(ev: SavingThrow) -> None:
        if ev.actor == who:
            c.world.effects.end(held, "used")

    c.watch(
        SavingThrow, used, until=When.ENCOUNTER, on=who,
        label="cf:wizard-implement",
    )


@power(
    "cf:wizard-rituals",
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
