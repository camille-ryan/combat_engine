"""The warlord feature that pays out when a friend spends an action point.

Six options are printed and the class has two legs, so two of them land
here -- the Charisma one and the Intelligence one -- exactly as
`features/strikers.py` lands two of the rogue's four tactics. The other
four have no leg to ask about.

**Both numbers are the card's.** The healing leg pays one-half the
warlord's level plus its Charisma modifier; the attack leg pays half its
Intelligence modifier. Neither is rounded up and neither has a floor.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    ActionPointSpent,
    ActionType,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "cf:warlord-marshal-f4",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def warlord_presence(c: Cast) -> None:
    """Whichever leg was taken, it fires on an ally's action point.

    Both numbers are the card's, not invented: the inspiring leg heals
    one-half your level + your Charisma modifier, and the tactical leg
    gives half the Intelligence modifier with no minimum. An earlier
    draft floored the second at 1, which is a warlord being paid for a
    stat it dumped.

    **The tactical leg's printed trigger is narrower than what is armed
    here.** It reads "spends an action point *to make an attack*", and
    `ActionPointSpent` carries the action type gained and nothing about
    what is done with it, so the attack half cannot be asked. The bonus is
    spent by the first attack roll either way, which is where the two
    readings come back together; a turn that spends a point and then does
    not swing keeps a bonus it should not have until the end of it.

    **Both legs print "from only one of them" for a party with two of
    these warlords in it, and neither says it here.** Nothing coordinates
    two traits armed on two different creatures, and a shared bonus kind
    would only cover the attack leg -- the heal has no kind to share. A
    second warlord therefore pays twice.

    A trait, so `Encounter._arm_traits` turns it on once. The watcher is
    kept for the whole fight rather than renewed, because the printed line
    has no duration -- it is simply what this warlord is.
    """
    me = c.me

    def spent(ev: ActionPointSpent) -> None:
        who = ev.actor
        if who == me or who not in c.allies() or not c.can_see(who):
            return
        if c.build("inspiring"):
            c.heal(c.cha_mod + c.level // 2, on=who)
        elif c.build("tactical"):
            # Half the Intelligence modifier, and **no floor**. The `max(1,
            # ...)` that was here is not on the card: a warlord with an
            # Intelligence of 11 gives nothing, which is the printed
            # consequence of dumping the stat the leg keys off.
            #
            # Untyped: the card names no bonus type. It was `power`, which
            # is the type the *initiative* leader feature prints, not this.
            c.bonus(
                "attack", c.int_mod // 2, kind="untyped",
                on=who, until=When.EOT, once=True,
            )

    c.watch(
        ActionPointSpent, spent, until=When.ENCOUNTER, on=me,
        label="cf:warlord-marshal-f4",
    )
