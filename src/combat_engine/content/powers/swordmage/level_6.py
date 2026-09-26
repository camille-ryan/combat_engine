"""Swordmage, level 6: the utilities.

`p16012` and `p3358` both want an aura that treats the two sides
differently. A zone's `difficult` is a kind of going, not a side, so the
rough ground is laid for everyone and then waived for my own side by name --
which is what `c.ignores_difficult(kind)` is for.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    When,
    Window,
    power,
)
from combat_engine.engine.events import EffectApplied, MoveStart
from combat_engine.engine.zones import Zone

_ELEMENTS_TEXT = "the element you ward against"


@power(
    "p10353",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE, Keyword.TELEPORTATION],
)
def p10353(c: Cast) -> None:
    """A movement mode, which is what "as an additional movement mode"
    prints. The leash -- ending beside an enemy -- has nothing behind it."""
    me = c.me
    stance = c.stance(label=c.ref)
    rider = c.mode("teleport", 3, until=When.ENCOUNTER, on=me)
    if rider is not None:
        stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))


@power(
    "p10435",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p10435(c: Cast) -> None:
    """A modifier lives on a creature, so "your allies, while adjacent" is
    one gated bonus per ally rather than an aura."""
    me = c.me
    stance = c.stance(label=c.ref)
    wanted = [AC, FORT, REF, WILL] if c.build("shielding") else [AC]
    for mate in c.allies():

        def near(ctx: dict, w: int = mate) -> bool:
            return c.adjacent_to(me, w)

        for what in wanted:
            rider = c.bonus(what, 1, on=mate, until=When.ENCOUNTER, when=near)
            if rider is not None:
                stance.on_end.append(
                    lambda r=rider: c.world.effects.end(r, "stance ended")
                )


@power(
    "p16012",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p16012(c: Cast) -> None:
    """The free action that switches it off is not a thing a header can
    declare, so the aura simply runs to the end of the fight."""
    ring = c.aura(2, until=When.ENCOUNTER, on=c.me, label=c.ref)
    zone = c.world.get(ring, Zone)
    if zone is not None:
        zone.difficult = c.ref
    for mate in [c.me, *c.allies()]:
        c.ignores_difficult(c.ref, on=mate, until=When.ENCOUNTER)


@power(
    "p1703",
    level=6,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
)
def p1703(c: Cast) -> None:
    for mate in c.within(1, side="ally"):
        c.bonus(AC, 2, on=mate, until=When.EONT)
        c.bonus(REF, 2, on=mate, until=When.EONT)


@power(
    "p3145",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE],
)
def p3145(c: Cast) -> None:
    """The "you do not expend it on one target" clause is bookkeeping about
    the use rather than anything that happens on the board."""
    c.mark(until=When.ENCOUNTER)


@power(
    "p3160",
    level=6,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3160(c: Cast) -> None:
    """The flight lasts the move and no longer, so the mode is clocked to
    the end of this turn."""
    far = c.speed_of()
    c.mode("fly", far, until=When.EOT, on=c.me)
    c.move(far)


@power(
    "p3357",
    level=6,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p3357(c: Cast) -> None:
    if not c.teleport(5):
        return
    close = c.within(1, side="enemy")
    if not close:
        return
    foe = c.choose(sorted(close), "you land beside")
    if foe is not None:
        c.bonus(
            "attack", 2, on=c.me, until=When.EOT, once=True,
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )


@power(
    "p3358",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.STANCE, Keyword.ZONE],
)
def p3358(c: Cast) -> None:
    """Only the first half is sayable. A teleport is refused at `MoveStart`,
    which fires before the creature has picked a square -- so an enemy
    *inside* the zone can be stopped and one teleporting *into* it cannot."""
    me = c.me
    stance = c.stance(label=c.ref)
    ring = c.aura(2, until=When.ENCOUNTER, on=me, label=c.ref)

    def refuse(ev: MoveStart) -> None:
        if ev.kind_ != "teleport" or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            ev.cancel("the zone holds")

    rider = c.watch(
        MoveStart, refuse, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=c.ref,
    )
    stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))
    stance.on_end.append(lambda: c.world.zones.end(ring, "stance ended"))


@power(
    "p3359",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3359(c: Cast) -> None:
    """`EffectApplied` says something landed but not which hold it was, so
    the penalty is set on whichever of the target's save-ends effects I own
    and have not already weighted."""
    me = c.me
    foes = set(c.enemies())

    def weigh(ev: EffectApplied) -> None:
        if ev.source != me or ev.target not in foes:
            return
        for eff in c.world.effects.of(ev.target):
            if eff.when is When.SAVE_ENDS and eff.source == me and eff.save_mod == 0:
                eff.save_mod = -2

    c.watch(EffectApplied, weigh, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p3938",
    level=6,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3938(c: Cast) -> None:
    c.move(12)


@power(
    "p4801",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p4801(c: Cast) -> None:
    """Switching the type later is a second minor action with no row of its
    own, so the choice made here stands."""
    kind = c.choose(
        [
            DamageType.ACID,
            DamageType.COLD,
            DamageType.FIRE,
            DamageType.LIGHTNING,
            DamageType.THUNDER,
        ],
        _ELEMENTS_TEXT,
    )
    if kind is not None and c.con_mod > 0:
        c.resist(c.con_mod, kind, until=When.ENCOUNTER, on=c.me)


@power(
    "p5748",
    level=6,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p5748(c: Cast) -> None:
    """`c.save` and `c.heal` both follow the target already, which is the
    right default here: the printed line is about them, not me."""
    if c.may("shake it off"):
        c.save()
    else:
        c.heal(5 + c.con_mod)
