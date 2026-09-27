"""Rogue feats.

The class's extra damage is `cf:rogue-scoundrel-f4`, named by ref in
five of these prerequisites -- so where a row *rides* on it the gap is
never the name. It is that nothing announces that the extra damage was
paid, and nothing reaches into the dice another row rolls. Both are
marked exactly.

The rest divides into the ordinary -- a critical with combat advantage,
a damage bonus beside an ally -- and three that turn on traps, which
the engine models and nothing on a board has ever placed (#74).
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    Hit,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import allies


def _crit_with_advantage(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A critical hit made **while you had combat advantage**.

    Read off the `Hit`'s own `AttackResult`, not by asking the board
    again: a one-shot grant of combat advantage has already been spent
    by the time the hit is announced, so asking afresh answers no for
    exactly the attacks these two rows are printed for.
    """
    result = getattr(ev, "result", None)
    return (
        ev.attacker == me
        and ev.critical
        and result is not None
        and result.advantage
    )


@power("f302", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit while you have combat advantage",
       on=Trigger(Hit, _crit_with_advantage, "you crit with advantage"))
def f302(c: Cast) -> None:
    c.grants_advantage(on=c.trigger.target, until=When.EONT)


@power("f307", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit while you have combat advantage",
       on=Trigger(Hit, _crit_with_advantage, "you crit with advantage"))
def f307(c: Cast) -> None:
    c.prone(on=c.trigger.target)


@power("f762", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f762(c: Cast) -> None:
    """Adjacency is asked when the blow lands rather than when the trait
    arms: a rogue moves, and where it was standing at the top of the
    fight is not where it is when it swings."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            c.adjacent(to=friend) for friend in allies(c.world, me)
        ),
    )


@power("f356", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f356(c: Cast) -> None:
    """The surprise round and the first round. `world.round` is 1 for
    both -- a surprise round is not counted separately -- so the gate is
    simply the first round, which is what the sentence comes to."""
    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.world.round <= 1)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.world.round <= 1 and not ctx.get("ranged", False),
    )


@power("f751", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_extra_damage()",))
def f751(c: Cast) -> None:
    """Trades the class's extra damage for a condition. Nothing announces
    that the extra damage was about to be paid, so there is no moment at
    which to offer the trade."""


@power("f763", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_extra_damage()",))
def f763(c: Cast) -> None:
    """Raises ongoing damage by one per die of the class's extra damage.
    Needs both the announcement and the count of dice rolled."""


@power("f185", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f185(c: Cast) -> None:
    """Raises the die another row rolls, d6 to d8. The dice are a string
    inside that row's body. Same gap as the ranger's f273."""


@power("f799", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(group=)",))
def f799(c: Cast) -> None:
    """Lets one weapon group count as another for a class's purposes.
    `c.as_implement` does this for one specific case by rewriting the
    group; the general form -- count as a light blade *for these rows
    only*, at a cost -- has no verb."""


@power("f370", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.shift_becomes_move()",))
def f370(c: Cast) -> None:
    """Turns any shift a power grants into a longer walk. A shift is
    taken inside the granting row's body; nothing intercepts one."""


@power("f750", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a target that has not yet acted",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me, "you hit"))
def f750(c: Cast) -> None:
    """"Has not yet acted" is the surprised condition, which the surprise
    round lays and the creature's first turn clears."""
    foe = c.trigger.target
    if c.is_(Condition.SURPRISED, on=foe):
        c.slide(1, on=foe)


@power("f767", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_power()",))
def f767(c: Cast) -> None:
    """A damage bonus on one named racial power used with combat
    advantage. The power is named in prose with no ref."""


@power("f784", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.penalised_by_me()",))
def f784(c: Cast) -> None:
    """Allies hit harder against enemies this rogue has rattled. The
    rattling keyword is real and `c.suffering` finds the hold it lays,
    so the ally bonus is written; what is dropped is the narrowing to a
    penalty *this* character caused, which `Mods` does not record."""
    me = c.me
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "attack", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") in c.suffering("rattled"),
        )


@power("f377", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f377(c: Cast) -> None:
    """A defence bonus against traps. `Trap` marks an entity as a hazard
    rather than a creature and `c.is_trap` asks, so this is writable --
    but nothing on a board has ever placed one (#74), so it will not
    come up until that changes."""
    from combat_engine.engine import AC, FORT, REF, WILL

    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: (
                ctx.get("attacker") is not None
                and c.is_trap(ctx["attacker"])
            ),
        )


@power("f775", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f775(c: Cast) -> None:
    """Finding traps and opening locks. Both are checks, not a fight."""
