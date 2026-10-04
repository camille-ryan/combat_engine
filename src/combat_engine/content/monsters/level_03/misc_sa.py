"""Monster abilities, level 3, the role-less block.

One stat block at this level prints no role at all. It is not a conjuration
or a mount -- it fights, and it is plainly a lurker in everything but the
printed word -- so it is written as an ordinary encounter monster.

Two conventions earn their keep here:

* "or 2d6 + 6 if the target is granting combat advantage" is read off the
  **roll** (`AttackResult.advantage`) and not asked of the board afterwards.
  `resolve.attack` clears `HIDDEN_FROM` the moment the attack is over, and a
  one-shot grant has already been spent, so asking again answers False
  exactly when the card means True.
* the header still carries the plain damage line as data; only the doubled
  branch is written out, because one expression cannot say both.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.skirmishers import _conceal
from combat_engine.content.monsters.level_03.skirmishers import _vanish_until_it_swings
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    Damage,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied
from combat_engine.engine.triggers import Trigger, targets_me

# --------------------------------------------------------------------------
# m6394
# --------------------------------------------------------------------------


@power(
    "m6394a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6394a0(c: Cast) -> None:
    """"When he rolls initiative" is the moment a trait is armed, so the hiding
    is simply done here. There is no check to roll: the printed line lowers
    what hiding *requires*, and what is left to say is the consequence."""
    _conceal(c)


@power(
    "m6394a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 6),
)
def m6394a1(c: Cast) -> None:
    res = c.strike()
    if res:
        if res.advantage:
            c.damage("2d6", 6)
        else:
            c.hit()


@power(
    "m6394a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 6),
)
def m6394a2(c: Cast) -> None:
    res = c.strike()
    if res:
        if res.advantage:
            c.damage("2d4", 6)
        else:
            c.hit()


@power(
    "m6394a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 6),
)
def m6394a3(c: Cast) -> None:
    """The swap is `c.swap`, which moves both creatures at once -- written as a
    slide of the target plus a shift of the caster it would be refused half the
    time, because each square is occupied until the other one has left it. The
    three-square step afterwards is a second, separate move."""
    foe = c.target
    res = c.strike()
    if res:
        if res.advantage:
            c.damage("2d6", 6)
        else:
            c.hit()
        if foe is not None:
            c.swap(foe)
    c.shift(3)


@power(
    "m6394a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m6394a4(c: Cast) -> None:
    """"Until he hits **or misses**" is the attack roll, not the outcome, which
    is why the veil is torn down on `AttackRolled`."""
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m6394a5",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger="he takes damage",
    on=Trigger(DamageApplied, targets_me, "he takes damage"),
)
def m6394a5(c: Cast) -> None:
    """Declared on `DamageApplied` and read with `targets_me`: the event names
    its subject `target`, so `about_me` -- which reads `actor` and only `actor`
    -- would be false forever.

    The database files this as a free action and the card prints an immediate
    reaction; the reaction is kept, because that is the window the printed line
    belongs in.
    """
    _vanish_until_it_swings(c, When.EONT)
