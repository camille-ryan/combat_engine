"""Ranger, level 5: the rest of the later-book rows.

Split from `level_5_b.py` only for length; the notes in that file's
docstring -- on ranged Requirements, on charges, and on the unmodelled beast
companion -- apply to these five as well.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    STR,
    Attack,
    Cast,
    DamageType,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Moved,
    Ranged,
    Trigger,
    UpTo,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import team

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_ENEMY_CLOSES = "an enemy moves adjacent to you"


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me."""
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p4390",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p4390(c: Cast) -> None:
    """Two attacks over one or two creatures; only a creature that takes both
    of them suffers the rider, which is why the choice waits until the
    shooting stops."""
    shots = 2 if (c.first and c.last) else 1
    landed = 0
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand=hand), c.attack_mod)
        else:
            c.half_damage(c.w(1, hand=hand), c.attack_mod)
    if landed < 2:
        return
    if c.choose(["burn", "daze"], f"{c.ref}: which rider") == "burn":
        c.ongoing(5)
    else:
        c.dazed(until=When.SAVE_ENDS)


@power(
    "p4392",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    no_provoke=True,
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p4392(c: Cast) -> None:
    """The Special line -- no opening for the target -- is the header's
    `no_provoke`, not anything the body does."""
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)


@power(
    "p4393",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4393(c: Cast) -> None:
    """Both riders need the beast companion, which is not modelled: the Beast
    line adds damage for four species, and the Effect line only lands when
    the companion is standing next to the quarry. Neither is approximated."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p4394",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.STANCE],
    requires=_has_ranged,
)
def p4394(c: Cast) -> None:
    """An immediate reaction is once a round, and nothing outside the
    dispatcher enforces that for a watch, so the latch is here.

    "Moves closer to you" is read off the two ends of the step rather than
    off the mover, which is the same test `warlock/level_1.py` uses.
    """
    stance = c.stance(label=c.ref)
    me = c.me
    mine = c.here
    spent: dict[int, int] = {}

    def loose(ev: Moved) -> None:
        foe = ev.actor
        if foe == me or foe not in c.enemies():
            return
        if distance(ev.to, mine) >= distance(ev.from_, mine):
            return
        if distance(ev.to, mine) > 5:
            return
        if spent.get(0) == c.world.round:
            return
        if not c.may("loose a shot", who=me):
            return
        spent[0] = c.world.round
        c.basic(on=foe, ranged=True)

    watching = c.watch(Moved, loose, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))


@power(
    "p4395",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p4395(c: Cast) -> None:
    """"Ignores the target's cover but not superior cover": the engine's
    cover penalty is the whole of what `ignore_cover` drops and superior
    cover is not modelled apart from it, so the exception has nothing left
    to exclude -- the reading `level_7.py`'s `p1419` settled.

    Whether the target was *already* the quarry has to be asked before the
    new designation is made, or it is always true.
    """
    already = c.is_quarry()
    if not c.strike(ignore_cover=True):
        c.half_damage(c.w(2), c.dex_mod)
        return
    c.damage(c.w(2), c.dex_mod)
    if already:
        c.damage(c.w(1), dtype=DamageType.UNTYPED)
    c.quarry(until=When.EONT)
