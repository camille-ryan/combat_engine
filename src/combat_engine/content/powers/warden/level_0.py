"""Warden, level 0: the two halves of the class's mark punishment.

Both answer the same printed Trigger and it needs two things said at once:
the attacker is carrying a mark **of mine**, and the attack leaves me out.
`c.marked` asks the first from inside a body and there is no ready-made
predicate for it, so `_marked_by_me` reads the relation directly; the second
is `leaves_me_out`, which reads the whole target list of the one power use
rather than this announcement's target.
"""

from __future__ import annotations

from combat_engine.engine import *

PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


def _marked_by_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    return who is not None and world.relations.holds(Relation.MARKED_BY, me, who)


@power(
    "p5093",
    level=0,
    cls="warden",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
    trigger="an enemy marked by you makes an attack that does not include you",
    on=Trigger(
        AttackDeclared,
        both(_marked_by_me, leaves_me_out),
        "an enemy marked by you attacks and leaves you out",
    ),
)
def p5093(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "p5094",
    level=0,
    cls="warden",
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=PRIMAL,
    trigger="an enemy marked by you within 5 squares attacks and does not include you",
    on=Trigger(
        AttackDeclared,
        both(_marked_by_me, leaves_me_out, enemy_within(5)),
        "an enemy marked by you within 5 squares attacks and leaves you out",
    ),
)
def p5094(c: Cast) -> None:
    """"Until the end of its turn" is `When.EOT`: the row answers an attack,
    so the turn running is the target's own."""
    c.slide(1)
    c.slowed(until=When.EOT)
    c.rooted(until=When.EOT)
