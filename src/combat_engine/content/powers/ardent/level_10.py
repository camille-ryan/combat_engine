"""Ardent, level 10: the utilities.

One printed row is absent: the one whose whole effect is knowing an enemy's
location and ignoring its cover and concealment for the rest of the encounter.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    REACTION,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Position,
    Ranged,
    SavingThrow,
    Trigger,
    TurnStart,
    When,
    ally_within,
    both,
    by_melee,
    either,
    get,
    power,
    spread,
    targets_me,
    targets_my_side,
)

PSIONIC = [Keyword.PSIONIC]
DEFENCES = (AC, FORT, REF, WILL)


def _friends(c: Cast, radius: int, *, mine: bool = False) -> list[int]:
    return [a for a in c.within(radius, side="ally") if mine or a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


def _saved(world: object, me: int, ev: object) -> bool:
    """You, and only on a success. `about_me` alone answers failures too."""
    return getattr(ev, "actor", None) == me and bool(getattr(ev, "saved", False))


@power(
    "p10291",
    level=10,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.HEALING],
)
def p10291(c: Cast) -> None:
    """Standing up has no method of its own, so the prone hold is ended
    directly -- which is what standing up is."""
    who = c.target
    if who is None:
        return
    was_dying = c.is_(Condition.DYING, on=who)
    c.heal(c.surge_value(who), on=who)
    if was_dying:
        c.heal(c.roll("2d10") + c.cha_mod, on=who)
    for eff in list(c.world.effects.of(who)):
        if Condition.PRONE in eff.conditions:
            c.world.effects.end(eff, "stands up")


@power(
    "p10292",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=PSIONIC,
)
def p10292(c: Cast) -> None:
    """"Against fear effects" is read off the row that laid the effect being
    saved against: the label starts with its ref, and the keywords are data."""

    def fearful(ctx: dict) -> bool:
        label = str(getattr(ctx.get("effect"), "label", ""))
        p = get(label.split()[0]) if label else None
        return p is not None and Keyword.FEAR in p.keywords

    c.bonus("attack", 2, until=When.EONT, kind="power")
    c.bonus("save", 2, until=When.EONT, when=fearful, kind="power")


@power(
    "p11121",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an attack damages you or an ally",
    on=Trigger(
        DamageRolled,
        either(targets_me, targets_my_side),
        "an attack damages you or an ally",
    ),
)
def p11121(c: Cast) -> None:
    """`DamageRolled` is a decision, answered before the damage lands, which is
    the only window in which reducing it means anything."""
    ev = c.trigger
    if ev is None or not c.first:
        return
    ev.amount = max(0, ev.amount - c.level)


@power(
    "p11122",
    level=10,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ZONE],
)
def p11122(c: Cast) -> None:
    """Neither `c.resist` nor `c.bonus` takes a sustain cost, so the hold owns
    the sustain and re-lays them. `c.save` picks an effect by label fragment and
    labels are refs, so the extra save is against whatever is standing."""
    area = spread({c.here}, 3)
    c.zone(area, until=When.SUSTAIN, sustain=MINOR)

    def shelter() -> None:
        for who in c.in_squares(area, side="ally"):
            c.resist(10, DamageType.PSYCHIC, on=who, until=When.EONT)
            c.bonus(WILL, 4, on=who, until=When.EONT, kind="power")
            for d in (AC, FORT, REF):
                c.bonus(d, 2, on=who, until=When.EONT, kind="power")

    shelter()
    hold = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    c.on_sustain(hold, shelter)

    def tick(ev: TurnStart) -> None:
        if ev.actor != c.me and ev.actor in c.in_squares(area, side="ally"):
            c.save(on=ev.actor)

    c.watch(TurnStart, tick, until=When.ENCOUNTER)


@power(
    "p12964",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="you succeed on a saving throw",
    on=Trigger(SavingThrow, _saved, "you succeed on a saving throw"),
)
def p12964(c: Cast) -> None:
    for d in DEFENCES:
        c.bonus(d, 2, until=When.EONT, kind="power")


@power(
    "p12965",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="an ally you can see succeeds on a skill check",
    out_of_combat=True,
)
def p12965(c: Cast) -> None:
    """Skill checks are not fought with and the engine keeps none, so both the
    trigger and the effect are outside a fight entirely."""
    if c.first:
        c.note(f"{c.ref}: +2 to each ally's next skill check")


@power(
    "p12966",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an ally within 5 squares of you hits with a melee attack",
    on=Trigger(
        Hit,
        both(ally_within(5), by_melee),
        "an ally within 5 squares hits with a melee attack",
    ),
)
def p12966(c: Cast) -> None:
    """On a `Hit`, `ally_within` reads the attacker -- which is the ally the
    printed line names."""
    who = getattr(c.trigger, "attacker", None)
    if who is not None and c.first:
        c.temp_hp(5 + c.cha_mod, on=who)


@power(
    "p12967",
    level=10,
    cls="ardent",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    trigger="an ally within 5 squares becomes bloodied or drops to 0 hit points",
    on=[
        Trigger(Bloodied, ally_within(5), "an ally within 5 squares is bloodied"),
        Trigger(Dropped, ally_within(5), "an ally within 5 squares drops"),
    ],
)
def p12967(c: Cast) -> None:
    """Both printed halves of the trigger are declared: half of it would look
    finished. The destination is named outright, so the teleport is given a
    range wide enough to reach it."""
    hurt = getattr(c.trigger, "actor", None)
    pool = [a for a in _friends(c, 5) if a != hurt]
    who = _pick(c, pool, "who is pulled across")
    pos = c.world.get(hurt, Position) if hurt is not None else None
    if who is None or pos is None:
        return
    free = [
        sq
        for sq in sorted(spread({pos.square}, 1))
        if sq != pos.square and not c.in_squares([sq])
    ]
    if free:
        c.teleport(40, who=who, to=free[0])
