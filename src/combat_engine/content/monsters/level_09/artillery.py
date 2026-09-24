"""Monster abilities, level 9: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=REF,
printed=14)` and `Damage("2d6", 10)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the eight levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; a printed range of "15/30" is a normal range and a
long one, and `Range` holds one number, so the **normal** range is written;
and a stat block printing no range at all means melee 1.

Four things this file had to settle.

**"Whichever defence is lower"** is now sayable: `AttackDeclared.vs` is read
back off the event, so a `Window.BEFORE` listener can move the blow from one
defence to the other after the target is known and before anything is
rolled. Comparing the two in the body and calling `c.attack` would have come
to the same number and taken the printed line off the card.

**"Targets nonreptiles"** is a target line no `Target` can say -- it carries
a side and a count and no type word -- so the header takes everyone in the
area and the body lets its own kind past. Written as a Requirement instead
it would stop the row being offered at all.

**"Recharges when first bloodied"** on top of a printed 6+ is both: the die
stays in the header, because that is what the card shows and what
`actions.recharge` rolls, and the sentence is armed as a watch. The two only
ever agree to make the row available sooner.

**A printed sight limit** -- "cannot see anything more than 3 squares away"
-- has nowhere to go. Vision is asked of the board rather than held on the
creature, and there is no method that narrows it; the damage half of that
row is written and the limit is noted. See the report.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Usage,
    When,
    Window,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit, Miss, OpportunityWindow
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import defence, grants_ca
from combat_engine.engine.triggers import Trigger, hits_me

#: The label the level 6 stat block's aura is created under. `c.aura` falls
#: back to the row's own ref when no label is given, so this is the name the
#: zone is actually carrying and the only way to recognise one.
_M719_AURA = "m719a0"


def _in_that_aura(c: Cast, who: int, label: str) -> bool:
    """Is that creature standing in an aura somebody else laid?

    Zones are entities with a label, and the occupants of each are diffed as
    anybody moves, so this is a lookup rather than a distance measured again
    against a creature whose aura may not even be centred on it any more.
    """
    return any(
        zone.label == label and who in c.world.zones.occupants(zid)
        for zid, zone in c.world.zones.all()
    )


def _softest(c: Cast, first: Defense, second: Defense) -> Effect:
    """Send this row's attack at whichever of two defences is lower.

    Armed for the length of the caster's turn and torn down by the caller.
    `AttackDeclared` is the seam: the target is settled by then and nothing
    has been rolled, and `vs` is read back off the event -- a listener that
    set its own local would have changed nothing.
    """
    me, ref = c.me, c.ref

    def choose(ev: AttackDeclared) -> None:
        if ev.attacker != me or ev.power != ref:
            return
        ctx = {"attacker": me, "target": ev.target, "power": ref}
        if defence(c.world, ev.target, second, ctx) < defence(c.world, ev.target, first, ctx):
            ev.vs = second

    return c.watch(
        AttackDeclared,
        choose,
        until=When.EOT,
        window=Window.BEFORE,
        on=me,
        label=f"{ref} softest",
    )


# ==========================================================================
# m141
# ==========================================================================


@power(
    "m141a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m141a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m141a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 10, dtype=DamageType.THUNDER),
)
def m141a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m141a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m141a2(c: Cast) -> None:
    """The printed target is "creatures in the blast", which is both sides."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m211
# ==========================================================================


@power(
    "m211a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m211a0(c: Cast) -> None:
    """Two expressions on one line and the header holds one, so the untyped
    half stays in the header and the burn is rolled here."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m211a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m211a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m3004
# ==========================================================================


@power(
    "m3004a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5),
)
def m3004a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m3004a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 3),
)
def m3004a1(c: Cast) -> None:
    """15/30 is a normal range and a long one, and the normal range is what
    gets written: the band it shoots in at no penalty, rather than a distance
    at a -2 the engine has no way to apply. Only the burn is poison."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3004a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=16),
)
def m3004a2(c: Cast) -> None:
    """No damage line at all: being tangled is the whole of the hit.

    The printed Requirement is a piece of equipment, and a monster's gear is
    not something the engine holds -- `c.wielding` reads a character's hands.
    Left off the header rather than declared as a gate that would be true
    always or false always, and noted instead.
    """
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    c.note("m3004a2: requires a net")


# ==========================================================================
# m3094
# ==========================================================================


@power(
    "m3094a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m3094a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m3094a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m3094a1(c: Cast) -> None:
    """"AC or Fortitude, whichever is lower" is the header's defence moved at
    declaration, which is the one moment the target is known and nothing has
    been rolled. The header keeps AC, so the card prints the defence the line
    leads with.

    The rider names another stat block's aura by id. That aura is a zone with
    a label, so standing in it is a lookup rather than a distance measured
    against a creature that may have wandered off.
    """
    guard = _softest(c, AC, FORT)
    try:
        if not c.strike():
            return
        c.hit()
        if _in_that_aura(c, c.target, _M719_AURA):
            c.weakened(until=When.EOTNT)
    finally:
        c.world.effects.end(guard, "the shot is over")


_M3094_STRUCK = "the m3094 is hit by an attack"


@power(
    "m3094a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=13),
    trigger=_M3094_STRUCK,
    on=Trigger(Hit, when=hits_me, text=_M3094_STRUCK),
)
def m3094a2(c: Cast) -> None:
    """No damage line: the blinding is the whole of the hit.

    The printed target is "nonreptiles", which no `Target` can say, so the
    burst takes everyone caught in it and its own kind is let past here. The
    second printed recharge -- when it is first bloodied -- is armed on top
    of the die the database files.
    """
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.is_kind("reptile"):
        return
    if c.strike():
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3094a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3094a3(c: Cast) -> None:
    """"Nonreptiles" again: the burst takes everyone and its own kind is let
    past here."""
    if c.is_kind("reptile"):
        return
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


# ==========================================================================
# m5054
# ==========================================================================


@power(
    "m5054a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5054a0(c: Cast) -> None:
    """A Stealth check made in circumstances that normally forbid one, and
    the engine rolls no Stealth: hiding here is a relation a row sets, not a
    check anything makes. Deliberately inert rather than given an invented
    mechanic."""
    c.note("m5054a0: can hide with concealment, not only with total concealment")


@power(
    "m5054a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m5054a1(c: Cast) -> None:
    """Unseen by the one it just cut, and by nobody else -- which is what
    `to=` narrows `c.invisible` to."""
    if c.strike():
        c.hit()
        c.invisible(to=c.target, until=When.EONT)


@power(
    "m5054a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m5054a2(c: Cast) -> None:
    """The rider narrows the victim's sight to three squares, and there is
    nothing on `Cast` that narrows sight: vision is asked of the board, and
    `c.blinded` is the whole of what the engine holds about not seeing. The
    damage is written and the limit is noted rather than approximated with a
    condition twice as harsh. See the report."""
    if c.strike():
        c.hit()
        c.note("m5054a2: the target cannot see past 3 squares until the m5054's next turn")


@power(
    "m5054a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
)
def m5054a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying the hold and the burn: applied
    separately the victim gets two saving throws and can shake off half of a
    thing the card prints as one."""
    if c.strike():
        c.condition(
            Condition.RESTRAINED,
            until=When.SAVE_ENDS,
            ongoing=(15, DamageType.NECROTIC),
        )


@power(
    "m5054a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage(
        "1d10", 7, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True
    ),
)
def m5054a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
    else:
        c.hit(half=True)


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m3114
# --------------------------------------------------------------------------


@power(
    "m3114a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=9, kind=MINION),
)
def m3114a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m3114a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3114a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    `kind="untyped"` deliberately: this and the next trait are both a flat +2
    to damage, and two bonuses sharing a kind do not add -- the larger wins.
    Written at the default they would come to +2 when both apply, where the
    card gives a creature caught by both a +4.
    """
    me = c.me

    def caught_out(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and grants_ca(c.world, victim)

    c.bonus(
        "damage", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=caught_out
    )


@power(
    "m3114a2",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3114a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    "Its melee attacks" is narrower than its attacks, and the damage context
    carries no reach -- it has `target`, `power`, `opportunity` and `charge`
    and nothing else -- so the reach is looked up from the ref the context
    does carry.

    The tally leaves the m3114 out: every printed line of this shape counts
    *its allies*, and the ally pool puts the creature itself in.
    """
    me = c.me

    def hemmed_in(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine import get

        p = get(ctx.get("power") or "")
        if p is None or p.reach.kind != "melee":
            return False
        victim = ctx.get("target")
        if victim is None:
            return False
        return sum(1 for a in c.within(1, of=victim, side="ally") if a != me) >= 2

    c.bonus(
        "damage", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=hemmed_in
    )


@power(
    "m3114a3",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3114a3(c: Cast) -> None:
    """A jump is a move the engine has no separate word for, so it is four
    squares of movement with the two printed riders wrapped round it.

    The bonus is gated on `opportunity`, which the attack context carries
    for exactly this. Who missed cannot be read off `Miss` -- it names the
    attacker, the target and the row and says nothing about the window -- so
    the openings are collected as they are offered and the misses matched
    against them.
    """
    me = c.me
    swinging: set[int] = set()

    def against_openings(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity"))

    def opened(ev: OpportunityWindow) -> None:
        if ev.provoker == me:
            swinging.add(ev.actor)

    def fumbled(ev: Miss) -> None:
        if ev.target == me and ev.attacker in swinging:
            c.grants_advantage(until=When.EOT, on=ev.attacker, to=me)

    guard = c.bonus(AC, 5, until=When.EOT, on=me, when=against_openings)
    windows = c.watch(OpportunityWindow, opened, until=When.EOT, on=me, label=f"{c.ref} open")
    misses = c.watch(Miss, fumbled, until=When.EOT, on=me, label=f"{c.ref} missed")
    try:
        c.move(4)
    finally:
        for hold in (guard, windows, misses):
            if hold is not None:
                c.world.effects.end(hold, "the jump is over")


# --------------------------------------------------------------------------
# m362
# --------------------------------------------------------------------------


@power(
    "m362a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=6, kind=MINION),
)
def m362a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
