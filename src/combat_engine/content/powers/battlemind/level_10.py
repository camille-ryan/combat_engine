"""Battlemind, level 10."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    DamageApplied,
    DamageRolled,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    ally_within,
    get,
    power,
    targets_me,
)

from . import PSIONIC


def _weapon_attack(ctx: dict[str, Any]) -> bool:
    """"Your weapon attacks". The damage context carries the row that dealt
    it as `power`, which is where the keywords are."""
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


@power(
    "p11175",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION, Keyword.POLYMORPH],
)
def p11175(c: Cast) -> None:
    """The move-action teleport is a power in its own right and `c.grant_row`
    needs a ref to grant, so it is dropped."""
    c.resist(5, until=When.ENCOUNTER)


@power(
    "p11176",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="you take damage from an attack",
    on=Trigger(DamageRolled, targets_me, "you take damage from an attack"),
)
def p11176(c: Cast) -> None:
    """`DamageRolled` is a proposal and refusing it is exactly "the damage is
    reduced to 0" -- everything else the attack does has already happened or
    happens after, which is the printed "subject to all other effects"."""
    c.cancel()


@power(
    "p12428",
    level=10,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p12428(c: Cast) -> None:
    """The four extra damage types are dropped: a modifier carries a number
    and not a type, and `c.vulnerable` is the wrong end of it."""
    c.bonus("damage", c.cha_mod, on=c.me, until=When.EONT, when=_weapon_attack)


@power(
    "p13060",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13060(c: Cast) -> None:
    """Printed as a minor action on one weapon, which is not a target the
    header can name, so it lands on the wielder. The brutal 1 property is
    dropped -- nothing rerolls low damage dice. The critical rider is the
    half that can be said, and `c.flat(c.roll(...))` is how an extra die is
    added inside a critical without being maximised."""
    def crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.flat(c.roll("1d10"), on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


@power(
    "p13061",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE],
)
def p13061(c: Cast) -> None:
    """Walls and ceilings are a climb speed equal to the walking one, which is
    what "without having to climb" comes to on a grid."""
    c.stance()
    c.mode("climb", c.speed_of(), until=When.ENCOUNTER)


@power(
    "p13062",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13062(c: Cast) -> None:
    """The Perception bonus is not a combat effect."""
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "p2639",
    level=10,
    cls="battlemind",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an adjacent ally takes damage",
    on=Trigger(DamageApplied, ally_within(1), "an adjacent ally takes damage"),
)
def p2639(c: Cast) -> None:
    """The ally to slide is the one the event was about; the dispatcher only
    aims a triggered row at an *enemy*, so it is read off `c.trigger`."""
    ev = c.trigger
    hurt = getattr(ev, "target", None) if ev is not None else None
    c.slide(1, on=hurt if hurt is not None else c.target)


@power(
    "p2640",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ILLUSION, Keyword.CONJURATION],
)
def p2640(c: Cast) -> None:
    """The +4 is written flat rather than gated on "an attack that doesn't
    include both you and the duplicate": the defence context names one
    target and not a power's whole target list, so the gate would be silently
    false. That makes this row stronger than printed. The duplicate's own
    destruction is dropped -- a conjuration has no hit points to lose."""
    c.conjure(label=c.ref, until=When.ENCOUNTER, sustain=None, speed=5)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.ENCOUNTER)
