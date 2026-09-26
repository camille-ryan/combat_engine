"""Shaman, level 6 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    UpTo,
    When,
    hits_my_companion,
    power,
)
from combat_engine.engine.ecs import World

from ._spirit import beside, friends, keyed

PRIMAL = [Keyword.PRIMAL]


def drops_me(world: World, me: int, ev: Any) -> bool:
    """Damage that took me to 0 hit points or fewer."""
    return getattr(ev, "target", None) == me and getattr(ev, "hp", 1) <= 0


@power(
    "p11359",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p11359(c: Cast) -> None:
    """"Move through spaces occupied by your enemies" is the phasing rule;
    the engine has no narrower version that lets a creature through bodies
    but not through walls."""
    c.phasing(on=c.target, until=When.EONT)


@power(
    "p3835",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=UpTo(2, "ally"),
    keywords=PRIMAL,
)
def p3835(c: Cast) -> None:
    c.save()


@power(
    "p3836",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p3836(c: Cast) -> None:
    """"One bloodied ally" is a targeting restriction the header cannot
    state, so it is a guard in the body."""
    mate = c.target
    if mate is not None and c.bloodied(on=mate):
        c.resist(5, on=mate, until=When.ENCOUNTER)


@power(
    "p9756",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.HEALING],
)
def p9756(c: Cast) -> None:
    """`Dropped` names only the creature that fell, never who felled it, so
    "whenever the target reduces an enemy to 0" is read off the damage that
    did it instead."""
    mate = c.target
    if mate is None:
        return

    def reap(ev: Any) -> None:
        if ev.source != mate or ev.hp > 0:
            return
        if ev.target not in c.enemies():
            return
        c.heal(5, on=mate)
        for foe in c.within(1, of=mate, side="enemy"):
            c.flat(2, dtype=DamageType.FIRE, on=foe)

    c.watch(DamageApplied, reap, until=When.ENCOUNTER, on=mate)


@power(
    "p9759",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    trigger="an enemy reduces you to 0 hit points or fewer",
    on=Trigger(
        DamageApplied, drops_me, "an enemy reduces you to 0 hit points or fewer"
    ),
)
def p9759(c: Cast) -> None:
    mate = c.target
    if mate is None or mate == c.me:
        return
    if c.may("spend a healing surge", who=mate):
        c.surge(on=mate)
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.bonus(
            "attack", 2, on=mate, until=When.EONT, kind="untyped",
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )


# -- the rows built round the spirit ----------------------------------------


@power(
    "p11365",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p11365(c: Cast) -> None:
    """Every clause lifts a restriction the engine does not impose: nothing
    holds the spirit to a range, and nothing asks for sight or line of
    effect between a shaman and its own spirit. There is no combat
    consequence left to write."""
    c.note(f"{c.ref}: perceives through the spirit, at any range")


@power(
    "p12530",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5, from_="companion"),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p12530(c: Cast) -> None:
    """The printed line bars calling the companion again until the end of
    your next turn. That wants an id to take away and the call is not a
    row here, so the dismissal is as far as it goes."""
    mate = c.target
    c.dismiss_companion()
    if mate is None:
        return
    if c.may("spend a healing surge", who=mate):
        c.surge(on=mate)
    c.bonus("attack", 1, on=mate, until=When.ENCOUNTER)
    for what in (AC, FORT, REF, WILL):
        c.bonus(what, 2, on=mate, until=When.ENCOUNTER)


@power(
    "p12873",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2, from_="companion"),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p12873(c: Cast) -> None:
    """The zone is laid out before the spirit goes, since the burst is
    measured from it."""
    ring = c.zone(c.area(), until=When.EONT)
    c.dismiss_companion()
    for mate in friends(c):
        c.bonus(
            "attack", 2, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: (
                w in c.world.zones.occupants(ring)
                and keyed(ctx, Keyword.FIRE, Keyword.RADIANT)
            ),
        )

    def bless(ev: Any) -> None:
        if ev.attacker not in friends(c) or c.int_mod <= 0:
            return
        if ev.attacker not in c.world.zones.occupants(ring):
            return
        if keyed({"power": ev.power}, Keyword.FIRE, Keyword.RADIANT):
            c.temp_hp(c.int_mod, on=ev.attacker)

    c.watch(Hit, bless, until=When.EONT, on=c.me)


@power(
    "p3847",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p3847(c: Cast) -> None:
    """`c.no_advantage` takes no gate, so the standing half goes to the
    allies beside the spirit as the row goes off rather than being read
    continuously."""
    mate = c.target
    if mate is not None and c.may("spend a healing surge", who=mate):
        c.surge(on=mate, bonus=c.roll("1d6"))
    for friend in beside(c):
        c.no_advantage(on=friend, until=When.ENCOUNTER)


@power(
    "p5545",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p5545(c: Cast) -> None:
    """"You and each ally in the burst" is two pools: the shaman is a
    target whether or not the spirit's burst reaches back to him."""
    mate = c.target
    if mate is not None and mate != c.companion():
        c.slide(max(1, c.wis_mod), on=mate)
    if c.first and c.me not in c.targets:
        c.slide(max(1, c.wis_mod), on=c.me)


@power(
    "p9757",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p9757(c: Cast) -> None:
    """"Can use second winds as a minor action" changes what an action
    costs, and there is no verb for that, so the healing is the row."""
    mate = c.target
    if mate is not None and mate != c.companion():
        c.heal(c.roll("1d6"), on=mate)


@power(
    "p9758",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="an enemy hits your spirit companion",
    on=Trigger(Hit, hits_my_companion, "an enemy hits your spirit companion"),
)
def p9758(c: Cast) -> None:
    """`Hit` does not carry which defence was attacked, so when the trigger
    cannot say, all four are raised. The outcome is recomputed from the die
    once the interrupt window closes, which is what lets a +4 turn the blow
    away."""
    spirit = c.companion()
    if spirit is None:
        return
    vs = getattr(c.trigger, "vs", None)
    for what in [vs] if vs is not None else [AC, FORT, REF, WILL]:
        c.bonus(what, 4, on=spirit, until=When.EOT, once=True)
