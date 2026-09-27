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

    # The other leg: somebody already carrying one of this wizard's
    # save-ends effects has a harder time shaking *that one* off.
    me = c.me
    victims = sorted(c.suffering())
    who = c.choose(victims, "cf:wizard-arcanist-f0: who finds it harder to shake off") \
        if victims else None
    if who is None:
        return

    # "An effect that lasts until the subject succeeds on a saving throw",
    # and the penalty is to the next save **against that effect**. The
    # effect is designated, not merely the creature: a wizard holding two
    # of them on one target used to spend the penalty on whichever save
    # came first, and a save against somebody else's effect spent it for
    # nothing at all.
    held_by_target = [
        eff
        for eff in c.world.effects.of(who)
        if eff.source == me and eff.when is When.SAVE_ENDS
    ]
    if not held_by_target:
        return
    against = c.choose(
        sorted(held_by_target, key=lambda eff: eff.id),
        "cf:wizard-arcanist-f0: which effect it must shake off",
    )
    if against is None:
        return

    def this_one(ctx: dict[str, Any]) -> bool:
        return ctx.get("effect") is against

    held = c.penalty("save", c.wis_mod, on=who, until=When.ENCOUNTER, when=this_one)
    if held is None:
        return

    # "Its **next** saving throw", which `once=True` cannot say: a one-shot
    # modifier is spent by watching `AttackRolled`, so a save penalty
    # written that way would be burned by the next attack anybody made and
    # never by the save it is for. `Effects.save` reads the modifiers and
    # then announces the throw, so ending it here spends it on the right one
    # -- and `SavingThrow.against` is the effect rendered, which is what
    # tells one of this creature's saves from another.
    label = str(against)

    def used(ev: SavingThrow) -> None:
        if ev.actor == who and ev.against == label:
            c.world.effects.end(held, "used")

    c.watch(
        SavingThrow, used, until=When.ENCOUNTER, on=who,
        label="cf:wizard-arcanist-f0",
    )


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
