"""Bard, level 10: the utilities."""

from __future__ import annotations

from combat_engine.engine import *

DEFENCES = (AC, FORT, REF, WILL)


def _my_row(ctx: dict) -> bool:
    row = get(str(ctx.get("power") or ""))
    return row is not None and row.cls == "bard"


def _ally_dropped(world: World, me: int, ev: Event) -> bool:
    """An enemy's blow has taken an ally to 0 or fewer.

    Declared on `DamageApplied` rather than on `Dropped`: the printed line
    names the attacking enemy and `Dropped` carries only the creature that
    fell.
    """
    mate = getattr(ev, "target", None)
    foe = getattr(ev, "source", None)
    if mate is None or foe is None or mate == me:
        return False
    mine = query.team(world, me)
    if query.team(world, mate) is not mine or query.team(world, foe) is mine:
        return False
    if getattr(ev, "hp", 1) > 0:
        return False
    return query.distance_between(world, me, mate) <= 20


@power(
    "p11111",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p11111(c: Cast) -> None:
    """`Healed` carries no power, so the top-up answers any healing this bard
    is the source of rather than only the class's own rows. The re-entry latch
    is the point: the extra healing is itself a `Healed`."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_my_row)
    inside: list[int] = []

    def more(ev: Healed) -> None:
        if ev.source != c.me or inside or ev.amount <= 0:
            return
        inside.append(1)
        try:
            c.heal(c.cha_mod, on=ev.target)
        finally:
            inside.clear()

    c.watch(Healed, more, until=When.ENCOUNTER, on=c.me, label="p11111")


@power(
    "p14471",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p14471(c: Cast) -> None:
    """`ConditionApplied` names its subject `target`, so the guard reads that
    and not `actor`. The keyword half of the bonus is dropped: an effect
    carries no keywords."""
    mate = c.target
    if mate is None:
        return

    def relief(ev: ConditionApplied) -> None:
        if ev.target == mate and ev.duration is When.SAVE_ENDS:
            c.save(on=mate, bonus=3)

    c.watch(ConditionApplied, relief, until=When.ENCOUNTER, on=mate, once=True, label="p14471")


@power(
    "p14472",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p14472(c: Cast) -> None:
    """The second sentence turns a class feature's healing into a free action.
    The bard has no such feature here, so only the healing is written."""
    c.heal(c.cha_mod)


@power(
    "p2384",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p2384(c: Cast) -> None:
    """"Lessens any penalty to attack rolls by 2" is dropped -- a modifier can
    be added but not clipped, and a flat +2 to attack would be a different
    card."""
    ring = c.aura(5, until=When.ENCOUNTER)
    for mate in c.allies():
        c.bonus(
            WILL, 2, on=mate, until=When.ENCOUNTER,
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring),
        )


@power(
    "p2385",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    out_of_combat=True,
)
def p2385(c: Cast) -> None:
    c.note("p2385: each target looks like some other humanoid of its size for an hour")


@power(
    "p2386",
    level=10,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p2386(c: Cast) -> None:
    if c.target is None:
        return
    c.invisible(on=c.target, until=When.EONT)
    c.slide(2)


@power(
    "p2388",
    level=10,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p2388(c: Cast) -> None:
    for mate in c.within(5, side="ally"):
        if mate != c.me:
            c.bonus("save", 2, on=mate, until=When.EONT)


@power(
    "p2828",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def p2828(c: Cast) -> None:
    """The keyword half of the bonus is dropped: an effect carries no keywords
    for the saving throw to ask about."""
    c.save()


@power(
    "p2829",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p2829(c: Cast) -> None:
    c.note("p2829: +5 Insight and Perception for you and allies within 5 squares")


@power(
    "p2996",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p2996(c: Cast) -> None:
    """One reroll per ally per turn, latched by round -- the second save is
    itself a `SavingThrow` and would otherwise answer itself."""
    used: dict[int, int] = {}

    def again(ev: SavingThrow) -> None:
        who = ev.actor
        if ev.saved or who == c.me or who not in c.within(5, side="ally"):
            return
        if used.get(who) == c.world.round:
            return
        used[who] = c.world.round
        c.save(on=who)

    c.watch(SavingThrow, again, until=When.ENCOUNTER, on=c.me, label="p2996")


@power(
    "p5002",
    level=10,
    cls="bard",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(20),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    trigger="an enemy attack reduces an ally within 20 squares of you to 0 hit points",
    on=Trigger(DamageApplied, _ally_dropped, "an enemy drops an ally within 20 squares"),
)
def p5002(c: Cast) -> None:
    mate = getattr(c.trigger, "target", None)
    foe = getattr(c.trigger, "source", None)
    if mate is None or foe is None:
        return
    if c.may("spend a healing surge", who=mate):
        c.surge(on=mate)
    for which in DEFENCES:
        c.penalty(which, 5, on=foe, until=When.EONT)


@power(
    "p5698",
    level=10,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p5698(c: Cast) -> None:
    c.bonus("attack", 2, until=When.EONT)


@power(
    "p5699",
    level=10,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p5699(c: Cast) -> None:
    """A defence cannot be overwritten, so everybody is lifted to the best of
    them with a held bonus. Done once for the whole use, off `c.targets`."""
    if not c.first:
        return
    crowd = list(c.targets)
    if not crowd:
        return
    best = {d: max(query.defence(c.world, who, d) for who in crowd) for d in DEFENCES}
    for who in crowd:
        for which in DEFENCES:
            short = best[which] - query.defence(c.world, who, which)
            if short > 0:
                c.bonus(which, short, on=who, until=When.EONT)
