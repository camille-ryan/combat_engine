"""Artificer, level 2: the utilities.

Both interrupts here are declared rather than quoted -- `ForcedMove` and
`Hit` are the two events that can actually be refused, and `c.cancel()` is
the whole body of each.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    SELF,
    AttackDeclared,
    Cast,
    CloseBurst,
    ForcedMove,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    power,
    targets_my_side,
)

from . import servant_struck


@power(
    "p10194",
    level=2,
    cls="artificer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    trigger="you or an ally are affected by a push, pull, or slide effect",
    on=Trigger(
        ForcedMove,
        targets_my_side,
        "you or an ally are pushed, pulled or slid",
    ),
)
def p10194(c: Cast) -> None:
    """`ForcedMove` is one of the five events that can be refused, and it
    names its subject `target`, so `targets_my_side` is the predicate that
    covers "you or an ally"."""
    c.cancel()


@power(
    "p4202",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p4202(c: Cast) -> None:
    """Handing the temporary hit points on to somebody else is the target's
    own later action and there is nothing that moves them; only the grant is
    written."""
    c.temp_hp(20, on=c.target)


@power(
    "p7642",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p7642(c: Cast) -> None:
    """The trade-in is offered on `AttackDeclared`, the last moment before
    the defence is read, and asked of the ally rather than of the caster --
    it is their bonus being spent. Declining is the default: giving up a
    whole encounter's +1 for one attack's +4 is rarely worth it."""
    ally = c.target
    ward = c.bonus(AC, 1, on=ally, until=When.ENCOUNTER, kind="power")
    if ward is None or ally is None:
        return

    def offer(ev: AttackDeclared) -> None:
        if ev.target != ally or ward.ended:
            return
        if not c.may("spend the ward for +4 against this attack", who=ally,
                     default=False):
            return
        c.world.effects.end(ward, "spent")
        c.bonus(AC, 4, on=ally, until=When.EONT, once=True, kind="untyped")

    c.watch(AttackDeclared, offer, until=When.ENCOUNTER)


@power(
    "p7643",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="one of your summoned creatures within 5 squares of you is hit",
    on=Trigger(Hit, servant_struck(5), "one of your summoned creatures is hit"),
)
def p7643(c: Cast) -> None:
    """Reads the master relation, which is what `c.summon` sets. No
    artificer summon is written yet, so on today's board nothing can arm
    this -- but a summon from anywhere else would."""
    c.cancel()


@power(
    "p7644",
    level=2,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p7644(c: Cast) -> None:
    c.save()


@power(
    "p7645",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p7645(c: Cast) -> None:
    """Magic item daily uses are a resource kept outside the fight, so this
    is deliberately inert rather than unwritten."""
    c.note("p7645: the next magic item daily power does not count against the day")


@power(
    "p14401",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p14401(c: Cast) -> None:
    """"Within 2 squares of the figurine" is an aura hung on the conjuration
    rather than on the caster, and `c.grants_in` is what makes a zone carry
    something rather than bite. The figurine's 5 squares of movement on a
    sustain is its `speed`; the +4 to Stealth is a skill bonus with no check
    to modify here."""
    figurine = c.conjure(
        at=c.origin,
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=5,
    )
    veil = c.aura(2, label=c.ref, on=figurine, until=When.SUSTAIN, sustain=MINOR)
    c.grants_in(veil, "concealment", 2, side="team", kind="untyped")
