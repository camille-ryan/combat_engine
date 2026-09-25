"""Avenger, level 6: utility, first half.

Every row in this file prints an entry requirement naming something the
engine does not model. That is an entry requirement and not a rider: without
it the row still has its whole printed Effect, so each is written ungated and
the requirement is in the report.

Two shapes repeat.

**Stances.** `c.stance(on=c.me, label=c.ref)` -- taking one ends the last.
Anything that has to stop when the stance does is clocked on the *encounter*
and taken down from `stance.on_end`: a second effect carrying `When.STANCE`
confuses `Effects.stance_of`, which is `fighter/level_5.py`'s finding.

**Printed triggers.** Declared with `on=Trigger(...)` and a predicate written
here when no ready-made one says the printed sentence. A trigger naming the
oath asks `sworn`, which reads the hold rather than any relation.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageType,
    Event,
    Hit,
    Keyword,
    Trigger,
    Usage,
    When,
    World,
    about_me,
    by_melee,
    get,
    power,
)
from combat_engine.engine.query import team

from .oath import sworn

DIVINE = [Keyword.DIVINE]

_DEFENCES = (AC, FORT, REF, WILL)

#: What "the condition ends" reaches for on `p11671`.
_STUCK = (Condition.SLOWED, Condition.IMMOBILIZED, Condition.RESTRAINED)

#: What `p11676` answers. Three conditions, one printed line.
_BROKEN = (Condition.DAZED, Condition.STUNNED, Condition.WEAKENED)


@power(
    "p11671",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p11671(c: Cast) -> None:
    """A condition is held up by the effect carrying it, so ending it is
    ending those effects -- whatever their duration, since the printed line
    does not ask for a saving throw.
    """
    me = c.me
    for effect in list(c.world.effects.of(me)):
        if any(card in _STUCK for card in effect.conditions):
            c.world.effects.end(effect, c.ref)
    c.shift(c.speed_of(), who=me)


@power(
    "p11672",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p11672(c: Cast) -> None:
    """Who is sworn against is read at the moment the defence is looked up,
    not when the stance is taken: the oath moves, and the four bonuses have
    to move with it.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)

    def stranger(ctx: dict[str, Any]) -> bool:
        attacker = ctx.get("attacker")
        return attacker is not None and not sworn(c.world, me, attacker)

    for d in _DEFENCES:
        held = c.bonus(
            d, 2, on=me, until=When.ENCOUNTER, kind="power", when=stranger
        )
        if held is not None:
            stance.on_end.append(
                lambda h=held: c.world.effects.end(h, "the stance ended")
            )


_MY_OATH_MELEE_HIT = "you hit your oath of enmity target with a melee attack"


def _oath_melee_hit(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "attacker", None) == me
        and sworn(world, me, getattr(ev, "target", None))
        and by_melee(world, me, ev)
    )


@power(
    "p11674",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[*DIVINE, Keyword.RADIANT],
    trigger=_MY_OATH_MELEE_HIT,
    on=Trigger(Hit, _oath_melee_hit, _MY_OATH_MELEE_HIT),
)
def p11674(c: Cast) -> None:
    """"Against the target" is the creature the avenger just hit, which is
    read off the event rather than asked of the oath again -- the oath can
    be re-sworn before the ally ever swings.
    """
    friend, foe = c.target, getattr(c.trigger, "target", None)
    if friend is None or foe is None:
        return
    c.bonus(
        "attack", 2, on=friend, until=When.EONT, kind="power", once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )

    def sear(ev: Hit) -> None:
        if ev.attacker == friend and ev.target == foe:
            c.flat(5, dtype=DamageType.RADIANT, on=foe)

    c.watch(
        Hit, sear, until=When.EONT, on=c.me, once=True, label=f"{c.ref} light",
    )


_STRANGER_LANDS_ON_ME = "an enemy that is not your oath of enmity target hits you"


def _stranger_lands_on_me(world: World, me: int, ev: Event) -> bool:
    """Declared on the roll rather than on the hit.

    `resolve.attack` re-reads the defence once the `AttackRolled` window
    closes and decides from that, so a defence bonus raised on `Hit` is
    raised after the only comparison it exists for.
    """
    who = getattr(ev, "attacker", None)
    result = getattr(ev, "result", None)
    return (
        getattr(ev, "target", None) == me
        and who is not None
        and bool(result and result.hit)
        and team(world, who) is not team(world, me)
        and not sworn(world, me, who)
    )


@power(
    "p11675",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_STRANGER_LANDS_ON_ME,
    on=Trigger(AttackRolled, _stranger_lands_on_me, _STRANGER_LANDS_ON_ME),
)
def p11675(c: Cast) -> None:
    for d in _DEFENCES:
        c.bonus(d, 4, on=c.me, until=When.EONT, kind="power", once=True)


_BROKEN_BY_AN_ATTACK = "you are dazed, stunned or weakened by an attack"


def _broken_by_an_attack(world: World, me: int, ev: Event) -> bool:
    """`ConditionApplied` names its subject `target`, so `about_me` is
    false on it forever. It carries no power, so "by an attack" is read as
    "by somebody other than yourself" -- the only part of the sentence the
    event can answer.
    """
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "condition", None) in _BROKEN
        and getattr(ev, "source", None) != me
    )


@power(
    "p11676",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_BROKEN_BY_AN_ATTACK,
    on=Trigger(ConditionApplied, _broken_by_an_attack, _BROKEN_BY_AN_ATTACK),
)
def p11676(c: Cast) -> None:
    """`Effects.apply` installs everything before it announces the
    condition, so the effect being answered is already live here and ending
    it takes the condition with it. `c.save` would take whichever save-ends
    effect it found first, which need not be this one -- and this one need
    not be save-ends at all.
    """
    card = getattr(c.trigger, "condition", None)
    for effect in c.world.effects.of(c.me):
        if not effect.ended and card in effect.conditions:
            c.world.effects.save(effect)
            return


_BLOODIED_BY_AN_ATTACK = "you are bloodied by an attack"


@power(
    "p11677",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
    trigger=_BLOODIED_BY_AN_ATTACK,
    on=Trigger(Bloodied, about_me, _BLOODIED_BY_AN_ATTACK),
)
def p11677(c: Cast) -> None:
    """The damage context carries `power` as the ref that dealt it, which is
    where "your avenger encounter and daily attack powers" is read.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)

    def mine(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return (
            p is not None
            and p.cls == "avenger"
            and p.usage in (Usage.ENCOUNTER, Usage.DAILY)
            and p.attack is not None
        )

    held = c.bonus(
        "damage", c.wis_mod, on=me, until=When.ENCOUNTER, kind="untyped", when=mine
    )
    if held is not None:
        stance.on_end.append(
            lambda: c.world.effects.end(held, "the stance ended")
        )


@power(
    "p11678",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.HEALING],
)
def p11678(c: Cast) -> None:
    """Hit points equal to a surge, without a surge being spent: the printed
    line names the value, not the expenditure.
    """
    c.heal(c.surge_value(), on=c.me)


@power(
    "p11679",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(5),
    target=NO_TARGET,
    keywords=[*DIVINE, Keyword.ZONE],
)
def p11679(c: Cast) -> None:
    """The lit ground is real; what it denies is not. Concealment is not a
    state this engine holds -- cover is worked out from two positions at the
    moment of an attack -- so the second sentence is noted.
    """
    c.zone(c.area(), until=When.ENCOUNTER)
    c.note(f"{c.ref}: nothing in the zone draws concealment, and there is none here")


@power(
    "p11680",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p11680(c: Cast) -> None:
    c.insubstantial(until=When.EONT, on=c.me)
    c.note(f"{c.ref}: you also have concealment, and there is none here")


@power(
    "p11681",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.ILLUSION],
)
def p11681(c: Cast) -> None:
    """"Or until you hit or miss" needs no writing: `resolve.attack` clears
    `HIDDEN_FROM` for whoever swung, which is the engine's own rule and ends
    this exactly where the printed line does.
    """
    c.invisible(on=c.me, until=When.EONT)
