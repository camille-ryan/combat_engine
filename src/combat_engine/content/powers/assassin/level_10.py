"""Assassin, level 10: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    AreaBurst,
    Cast,
    CloseBurst,
    DamageApplied,
    Hit,
    InitiativeRolled,
    Keyword,
    Trigger,
    When,
    about_me,
    hits_me,
    power,
)


@power(
    "p12455",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(5),
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p12455(c: Cast) -> None:
    """Targeting is "you and each ally within 5", which no single header target
    says, so the burst is walked in the body and the same walk is what each
    sustain repeats."""

    def wave() -> None:
        c.shift(2)
        for mate in c.within(5, side="ally"):
            if mate != c.me:
                c.shift(2, who=mate)

    wave()
    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MOVE), wave)


@power(
    "p12564",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 5),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.ZONE],
)
def p12564(c: Cast) -> None:
    """The lightly obscured half needs a concealment verb there is none of.
    The zone is still laid down, because the row's second power -- the free
    action that pulls you back into it when you are hurt -- is hung on it, and
    that half is written as a watch rather than as a second row, the spec
    giving both halves the same id."""
    area = c.area()
    c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def bolt_home(ev: DamageApplied) -> None:
        if ev.target != c.me:
            return
        free = [s for s in area if not c.in_squares([s])]
        if free:
            c.teleport(5, to=sorted(free)[0])

    c.watch(DamageApplied, bolt_home, until=When.ENCOUNTER)


@power(
    "p13808",
    level=10,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    out_of_combat=True,
)
def p13808(c: Cast) -> None:
    c.note("p13808: see and hear from a chosen square within 5, as well as your own")


@power(
    "p13809",
    level=10,
    cls="assassin",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
)
def p13809(c: Cast) -> None:
    """Line of sight is not required and an illegal destination negates the
    teleport; `c.teleport` already refuses squares the mover cannot stand in."""
    c.teleport(5)


@power(
    "p15916",
    level=10,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW],
    out_of_combat=True,
)
def p15916(c: Cast) -> None:
    c.note("p15916: a fresh disguise, and +2 to the Bluff checks that keep it")


@power(
    "p9439",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9439(c: Cast) -> None:
    c.phasing(on=c.me, until=When.EOT)
    c.shift(6)


@power(
    "p9440",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    trigger="an enemy hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def p9440(c: Cast) -> None:
    """Only the escape is written. The second half stores a move action to be
    spent once at any point before the end of the encounter, with its bonuses
    riding on having spent it, and nothing can hold an action like that."""
    c.teleport(10)


@power(
    "p9441",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p9441(c: Cast) -> None:
    """The encounter-long veil is ended by hand when the first hit lands: a
    second, shorter effect laid over it would not have shortened it, because
    two holds of the same relation both stand until their own clocks run."""
    c.bonus("damage", 4, on=c.me, until=When.ENCOUNTER, once=True, kind="power")
    veil = c.invisible(on=c.me, until=When.ENCOUNTER)

    def struck(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if veil is not None:
            c.world.effects.end(veil, "hit an enemy")
        c.invisible(on=c.me, until=When.EONT)

    c.watch(Hit, struck, until=When.ENCOUNTER, once=True)
