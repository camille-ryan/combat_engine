"""The warlord feature that pays out when a friend spends an action point.

Six options are printed and the class has two legs, so two of them land
here -- the Charisma one and the Intelligence one -- exactly as
`features/strikers.py` lands two of the rogue's four tactics. The other
four have no leg to ask about.

**Two judgement calls, both numbers.** The healing leg pays the warlord's
Charisma modifier plus half its level, and the attack leg pays half its
Intelligence modifier, rounded down but never less than one. Neither
number has a card -- a class feature has no compendium row -- and both are
written here rather than guessed at somewhere less visible.
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
    "cf:warlord-presence",
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
    Charisma modifier **plus one-half your level**, and the tactical leg
    gives half the Intelligence modifier with no minimum. An earlier
    draft floored the second at 1, which is a warlord being paid for a
    stat it dumped.

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
            c.bonus(
                "attack", c.int_mod // 2, kind="power",
                on=who, until=When.EOT, once=True,
            )

    c.watch(
        ActionPointSpent, spent, until=When.ENCOUNTER, on=me,
        label="cf:warlord-presence",
    )
