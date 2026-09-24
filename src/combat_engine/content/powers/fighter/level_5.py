"""Fighter, level 5: daily attacks."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Condition,
    DamageType,
    Keyword,
    Melee,
    Mod,
    TurnStart,
    When,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

#: What stops a fighter taking opportunity attacks, which is the condition
#: `p1436` hangs its damage on. The same pair the reaction policy checks.
_NO_OPPORTUNITIES = (Condition.DAZED, Condition.STUNNED, Condition.UNCONSCIOUS)


@power(
    "p1433",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1433(c: Cast) -> None:
    """"Save ends both" is one effect, not two.

    `c.ongoing` and `c.penalty` would each roll their own save, so the
    target could shake off half the line; the ongoing damage and the
    modifier are applied together instead, and one save takes both.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    c.world.effects.apply(
        foe,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} ongoing 5 and AC-2",
        ongoing=(5, DamageType.UNTYPED),
        mods=[(foe, Mod(what=AC.value, value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "p1434",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1434(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "p1436",
    level=5,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*MARTIAL_WEAPON, Keyword.STANCE],
)
def p1436(c: Cast) -> None:
    """A stance that bites whoever starts its turn in reach.

    The watcher hangs off the stance rather than carrying `When.STANCE`
    itself: a second stance-clocked effect confuses `Effects.stance_of`, and
    taking another stance has to stop the biting with it. `p1522` settled
    that arrangement.

    "Only if you're able to make opportunity attacks" is read as the
    conditions that stop one, which is what the reaction policy checks
    before offering the window.
    """
    me = c.me
    stance = c.stance(label=c.ref)

    def bite(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies() or not c.adjacent(ev.actor):
            return
        if any(c.is_(cond, on=me) for cond in _NO_OPPORTUNITIES):
            return
        c.damage(c.w(1), on=ev.actor)

    watching = c.watch(
        TurnStart, bite, until=When.ENCOUNTER, on=me, label=f"{c.ref} reprisal"
    )
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))
