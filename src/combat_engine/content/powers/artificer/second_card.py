"""Artificer: the second stat blocks printed beside the infusions.

Four of these are bursts centred on the ally the parent infused, and one is
a teleport to that ally's side. A close burst in the header is always
centred on the caster, so each picks its own targets around the creature
the parent named: `NO_TARGET` and a loop, rather than a header that would
aim at the wrong square.

Each parent now leaves two holds. One on the caster labelled with its own
ref is "until the end of the encounter, you can use ..." -- the Requirement
these read through `cards.active`. One on the infused ally labelled
`<ref> anchor` is which ally it was, which nothing else records.

`p13442b` is the odd one: its attacker is the parent's conjuration, so the
gate is that the conjuration is standing rather than a hold on the caster.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine.components import Conjuration
from combat_engine.engine.query import distance_between


def _anchor(world: World, me: int, ref: str) -> int | None:
    """Whoever the parent infused, from the hold it left on them."""
    for eff in world.effects.live.values():
        if eff.source == me and eff.label == f"{ref} anchor":
            return eff.owner
    return None


def _infusion_up(ref: str, within: int = 5):  # noqa: ANN202
    """The Requirement, plus the parent's "if the target is within N"."""
    standing = active(ref)

    def check(world: World, eid: int) -> bool:
        if not standing(world, eid):
            return False
        ward = _anchor(world, eid, ref)
        return ward is not None and distance_between(world, eid, ward) <= within

    return check


def _conjuration(world: World, me: int, ref: str) -> int | None:
    for eid in list(world.having(Conjuration)):
        made = world.get(eid, Conjuration)
        if made is not None and made.by == me and made.ref == ref:
            return eid
    return None


def _conjured(ref: str):  # noqa: ANN202
    def check(world: World, eid: int) -> bool:
        return _conjuration(world, eid, ref) is not None

    return check


@power(
    "p10191b",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.FIRE],
    once_per_round=True,
    requires=_infusion_up("p10191"),
    requires_text="the p10191 infusion must be up, on an ally within 5 squares",
)
def p10191b(c: Cast) -> None:
    """Printed Daily, but its own Special is "only once per turn" and the
    parent grants it once a round for the whole encounter -- one use would
    contradict both, so the frequency that can be said is at-will with a
    round latch, and the daily budget is the parent's.

    "Your implement's enhancement bonus" is the best enhancement in hand.
    Everything `chargen` deals is plain, so it comes to the printed 5."""
    ward = _anchor(c.world, c.me, "p10191")
    if ward is None:
        return
    hurt = 5 + max((w.enhancement for w in c.held()), default=0)
    for foe in c.within(1, of=ward, side="enemy"):
        c.flat(hurt, dtype=DamageType.FIRE, on=foe)
        c.mark(on=foe, by=ward, until=When.EONT)


@power(
    "p13442b",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[
        Keyword.ARCANE,
        Keyword.CONJURATION,
        Keyword.ILLUSION,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
    ],
    attack=Attack(INT, vs=WILL),
    requires=_conjured("p13442"),
    requires_text="the p13442 conjuration must be standing",
)
def p13442b(c: Cast) -> None:
    """The conjuration swings, so the target is picked from what stands next
    to *it*: a melee reach in the header is measured from the caster and no
    header field says otherwise.

    "Grants combat advantage to all attackers" is handed to the caster's
    whole side -- the relation names beneficiaries one at a time and
    `to="allies"` is as wide as it goes."""
    ghost = _conjuration(c.world, c.me, "p13442")
    if ghost is None:
        return
    pool = [foe for foe in c.enemies() if c.adjacent_to(ghost, foe)]
    foe = c.choose(pool, "who it reaches for") if pool else None
    if foe is None:
        return
    if c.strike(on=foe, from_=ghost):
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC, on=foe)
        c.grants_advantage(on=foe, to="allies", until=When.EOTNT)


@power(
    "p10197b",
    level=5,
    cls="artificer",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
    once_per_round=True,
    requires=_infusion_up("p10197", 10),
    requires_text="the p10197 power must be active, its ally within 10 squares",
)
def p10197b(c: Cast) -> None:
    """The printed line puts no limit on the hop itself, only on how far the
    ally may be, so the allowance is the ally's 10 plus the square beside
    them."""
    ally = _anchor(c.world, c.me, "p10197")
    spot = c.world.get(ally, Position) if ally is not None else None
    if spot is None:
        return
    for sq in sorted(spread({spot.square}, 1) - {spot.square}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            c.teleport(11, to=sq)
            return


@power(
    "p10199b",
    level=5,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=AC),
    once_per_round=True,
    requires=_infusion_up("p10199"),
    requires_text="the p10199 infusion must be up, on an ally within 5 squares",
)
def p10199b(c: Cast) -> None:
    """One target out of the burst, so the decider picks it; the push is
    away from the infused ally, which is what the anchor square is for."""
    ward = _anchor(c.world, c.me, "p10199")
    if ward is None:
        return
    pool = c.within(2, of=ward, side="enemy")
    foe = c.choose(pool, "who the thunder catches") if pool else None
    if foe is None:
        return
    if c.strike(on=foe, from_=ward):
        c.damage("1d10", c.int_mod, dtype=DamageType.THUNDER, on=foe)
        here = c.world.get(ward, Position)
        c.push(2, on=foe, anchor=here.square if here is not None else None)


@power(
    "p10205b",
    level=9,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=FORT),
    once_per_round=True,
    requires=_infusion_up("p10205"),
    requires_text="the p10205 infusion must be up, on an ally within 5 squares",
)
def p10205b(c: Cast) -> None:
    ward = _anchor(c.world, c.me, "p10205")
    if ward is None:
        return
    here = c.world.get(ward, Position)
    for foe in c.within(2, of=ward, side="enemy"):
        if c.strike(on=foe, from_=ward):
            c.damage("1d10", c.int_mod, dtype=DamageType.LIGHTNING, on=foe)
            c.pull(1, on=foe, anchor=here.square if here is not None else None)
