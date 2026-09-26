"""Bard, level 6: the utilities."""

from __future__ import annotations

from combat_engine.engine import *


def _misses_ally(world: World, me: int, ev: Event) -> bool:
    mate = getattr(ev, "target", None)
    if mate is None or mate == me:
        return False
    if query.team(world, mate) is not query.team(world, me):
        return False
    return query.distance_between(world, me, mate) <= 10


def _hits_ally(world: World, me: int, ev: Event) -> bool:
    mate = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if mate is None or foe is None or mate == me:
        return False
    mine = query.team(world, me)
    if query.team(world, mate) is not mine or query.team(world, foe) is mine:
        return False
    return query.distance_between(world, me, mate) <= 10


@power(
    "p12515",
    level=6,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p12515(c: Cast) -> None:
    """The lasting half -- "can teleport 1 square as a minor action" -- is
    dropped: it is a new action the target owns, and nothing grants one."""
    if c.target is not None:
        c.teleport(6, who=c.target)


@power(
    "p14464",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p14464(c: Cast) -> None:
    if not c.save(bonus=2):
        c.temp_hp(c.cha_mod)


@power(
    "p14465",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p14465(c: Cast) -> None:
    """`c.may` asks the creature whose surge it is, which is the target here."""
    if c.may("spend a healing surge") and c.surge():
        c.temp_hp(c.surge_value())


@power(
    "p2361",
    level=6,
    cls="bard",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    trigger="an attack misses an ally within 10 squares of you",
    on=Trigger(Miss, _misses_ally, "an attack misses an ally within 10 squares"),
)
def p2361(c: Cast) -> None:
    """Aimed off the trigger rather than through a header target: the printed
    target is "each ally missed by the triggering attack", and an attack is
    announced once per target, so that is the one the event names."""
    mate = getattr(c.trigger, "target", None)
    if mate is not None:
        c.heal(c.level // 2 + c.int_mod, on=mate)


@power(
    "p2372",
    level=6,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p2372(c: Cast) -> None:
    c.slide(2)


@power(
    "p2373",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p2373(c: Cast) -> None:
    given = 3 + c.con_mod

    def reward(ev: Hit) -> None:
        if ev.attacker in c.allies() and ev.attacker in c.within(5, side="ally"):
            c.temp_hp(given, on=ev.attacker)

    c.watch(Hit, reward, until=When.EONT, on=c.me, label="p2373")


@power(
    "p2993",
    level=6,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p2993(c: Cast) -> None:
    """The kept die is spent on an ally's attack roll, which is the one kind of
    d20 a listener can still reach: the result is re-read after the roll is
    announced, so a replacement there still decides the outcome."""
    kept = max(c.roll("1d20"), c.roll("1d20"), c.roll("1d20"))
    spent: list[int] = []

    def lend(ev: AttackRolled) -> None:
        if spent or ev.attacker not in c.allies():
            return
        if ev.attacker not in c.within(10, side="ally"):
            return
        res = getattr(ev, "result", None)
        if res is None or res.natural >= kept:
            return
        if not c.may("use the kept roll", who=c.me):
            return
        spent.append(1)
        res.total += kept - res.natural
        res.natural = kept

    c.watch(AttackRolled, lend, until=When.ENCOUNTER, on=c.me, label="p2993")


@power(
    "p5689",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="an attack hits an ally",
    on=Trigger(Hit, _hits_ally, "an attack hits an ally"),
)
def p5689(c: Cast) -> None:
    """Softened on the `DamageRolled` before it is applied rather than with
    `c.resist`, which would shave every other blow the ally took as well."""
    mate = getattr(c.trigger, "target", None)
    if mate is None:
        return
    cut = 5 + c.cha_mod

    def soften(ev: DamageRolled) -> None:
        if ev.target == mate:
            ev.amount = max(0, ev.amount - cut)

    c.watch(
        DamageRolled, soften, until=When.EOT, on=mate, once=True,
        window=Window.BEFORE, label="p5689",
    )


@power(
    "p5692",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p5692(c: Cast) -> None:
    """The extra square of shifting is dropped -- a shift's distance is not a
    held modifier, so there is no key to raise."""
    c.bonus("speed", 4, until=When.EONT, kind="power")
