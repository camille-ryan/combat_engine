"""Monster abilities, level 6, minions.

Twenty-three stat blocks, thirty-eight rows. Eight of the twenty-three print
no ability at all and have nothing to decorate: m1985, m2780, m314, m3458,
m4188, m5501, m6115, m705.

Conventions, inherited from the level 1-5 minion sweeps:

* a minion's damage is a flat number in the header, `Damage("", n,
  kind=MINION)`, and the body calls `c.hit()`. Its one hit point is in the
  database;
* a card printing two numbers for one blow ("7 damage, or 8 when charging")
  keeps the base in the header and adds the difference with `c.flat`;
* "two others of its kind within N squares" counts by `Ident.ref`, because
  every creature on the board may share a type word and the sentence is
  about this stat block;
* a card that prints no range at all is melee 1; a printed band of "15/30"
  or "6/12" takes the short number;
* `c.mark`, never `c.condition(Condition.MARKED, ...)`.

One block (`m5092`) prints one trait covering three different named
sub-templates -- vulture, boar, drake -- sharing a single ref here, and
nothing in the loaded numbers says which of the three this particular
creature is. See its own row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_03.skirmishers_sa import _mobile_attack
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Position,
    Powers,
    Ranged,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared, Dropped, Miss, Moved, TurnStart
from combat_engine.engine.grid import distance as square_distance
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import creatures, distance_between, has_combat_advantage, is_, team
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _ref_of(c: Cast, who: int) -> str:
    ident = c.world.get(who, Ident)
    return ident.ref if ident is not None else ""


def _knows(c: Cast, who: int, ref: str) -> bool:
    powers = c.world.get(who, Powers)
    return powers is not None and ref in powers.known


_PINNED_FOUR = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


def _row_reach_kind(ev: AttackDeclared) -> str:
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row.reach.kind if row is not None else ""


def _redirect_gate(world: World, me: int, ev: AttackDeclared, *kinds: str) -> bool:
    """"An enemy makes a [kind] attack against an ally adjacent to it" --
    read off the row that carried the attack, since the event itself names
    no reach kind. Shared by `m5827a3` (melee only) and `m6425a2` (melee or
    ranged)."""
    attacker = ev.attacker
    if attacker is None or attacker == me or team(world, attacker) is team(world, me):
        return False
    if _row_reach_kind(ev) not in kinds:
        return False
    victim = ev.target
    return (
        victim != me
        and team(world, victim) is team(world, me)
        and distance_between(world, victim, me) <= 1
    )


# ==========================================================================
# m1033
# ==========================================================================


@power(
    "m1033a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 3, kind=MINION),
)
def m1033a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1033a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1033a1(c: Cast) -> None:
    """A collective trait every copy of this creature carries. Only the
    lowest-eid one among three or more adjacent to the starting creature
    pays it out, so a swarm of them does not apply the printed effect once
    per copy."""
    me = c.me

    def check(ev: TurnStart) -> None:
        if ev.ghost:
            return
        starter = ev.actor
        near = [
            w for w in creatures(c.world)
            if _ref_of(c, w) == "m1033" and distance_between(c.world, starter, w) <= 1
        ]
        if len(near) < 3 or me != min(near):
            return
        c.condition(Condition.IMMOBILIZED, on=starter, until=When.EOT)
        c.flat(5, on=starter)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1035
# ==========================================================================


@power(
    "m1035a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 4, kind=MINION),
)
def m1035a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m115898
# ==========================================================================


@power(
    "m115898a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115898a0(c: Cast) -> None:
    """"Living enemies take a -2 penalty to attack rolls while in the
    aura" -- asked fresh off distance and kind each time rather than kept
    as a stale membership list."""
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    me = c.me
    for foe in c.enemies():
        c.penalty(
            "attack", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                distance_between(c.world, me, f) <= 1
                and not (c.is_kind("undead", on=f) or c.is_kind("construct", on=f))
            ),
        )


@power(
    "m115898a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m115898a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m115898a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is targeted by a close or an area attack",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: (
            ev.target == m and _row_reach_kind(ev) in ("close_burst", "close_blast", "area_burst")
        ),
        "it is targeted by a close or an area attack",
    ),
)
def m115898a2(c: Cast) -> None:
    c.shift(2)


# ==========================================================================
# m115915
# ==========================================================================


@power(
    "m115915a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("", 7, dtype=DamageType.NECROTIC, kind=MINION),
)
def m115915a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power("m115915a1", level=6, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m115915a1(c: Cast) -> None:
    c.shift(6)


# ==========================================================================
# m1161
# ==========================================================================


@power(
    "m1161a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 4, kind=MINION),
)
def m1161a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1161a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1161a1(c: Cast) -> None:
    """"+2 power bonus to all defenses while at least two other human
    cultists are within 5 squares" -- counted by `Ident.ref`."""
    mine = _ref_of(c, c.me)

    def enough(_ctx: dict[str, Any]) -> bool:
        return len([
            w for w in creatures(c.world)
            if w != c.me and _ref_of(c, w) == mine and distance_between(c.world, c.me, w) <= 5
        ]) >= 2

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, kind="power", until=When.ENCOUNTER, when=enough)


# ==========================================================================
# m1824
# ==========================================================================


@power(
    "m1824a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 6, kind=MINION),
)
def m1824a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1824a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("", 6, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m1824a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


# ==========================================================================
# m4476
# ==========================================================================


@power(
    "m4476a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m4476a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m4476a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4476a1(c: Cast) -> None:
    """"Ends his or her move at least 4 squares from where the move
    started" -- measured on `Moved`, the only movement event carrying
    both the starting square and the kind of step."""
    me = c.me

    def far_move(ev: Moved) -> None:
        if ev.actor != me or ev.kind_ not in ("walk", "shift") or ev.from_ is None:
            return
        pos = c.world.get(me, Position)
        if pos is None:
            return
        if square_distance(ev.from_, pos.square) >= 4:
            c.bonus("damage", 3, on=me, until=When.SONT)

    c.watch(Moved, far_move, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4476a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4476a2(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# ==========================================================================
# m4732
# ==========================================================================


@power(
    "m4732a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m4732a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4732a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 4, kind=MINION),
)
def m4732a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5092
# ==========================================================================


@power(
    "m5092a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.variant()",),
)
def m5092a0(c: Cast) -> None:
    """The card names three different sub-templates -- vulture, boar,
    drake -- sharing this one ref, and nothing in the loaded numbers (no
    fly speed, no distinguishing stat) says which one this particular
    creature is. Granting any of the three clauses unconditionally would
    be wrong for whichever templates it is not."""


@power(
    "m5092a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("", 7, kind=MINION),
)
def m5092a1(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m5092a2",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5092a2(c: Cast) -> None:
    for foe in c.within(2, side="enemy"):
        c.flat(3, dtype=DamageType.NECROTIC, on=foe)


# ==========================================================================
# m5300
# ==========================================================================


@power(
    "m5300a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m5300a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.charge:
            c.flat(1)


@power("m5300a1", level=6, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m5300a1(c: Cast) -> None:
    c.shift(1)
    c.move(5, at="fly")


# ==========================================================================
# m5493
# ==========================================================================


@power("m5493a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5493a0(c: Cast) -> None:
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("ranged")))


@power(
    "m5493a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m5493a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5493a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m5493a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5493a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger="it is missed by an attack",
    on=Trigger(Miss, targets_me, "it is missed by an attack"),
)
def m5493a3(c: Cast) -> None:
    c.jump(3)


# ==========================================================================
# m5827
# ==========================================================================


@power("m5827a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5827a0(c: Cast) -> None:
    """"An ally who also has this trait" -- checked by whether the dying
    ally carries this same ref's row, not by type word."""
    me, ref = c.me, c.ref

    def fallen(ev: Dropped) -> None:
        if ev.actor == me or not _knows(c, ev.actor, ref):
            return
        if distance_between(c.world, me, ev.actor) <= 5:
            c.bonus("attack", 2, on=me, kind="power", until=When.EONT)

    c.watch(Dropped, fallen, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5827a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m5827a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5827a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m5827a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5827a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits an ally adjacent to it with a melee attack",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: _redirect_gate(w, m, ev, "melee"),
        "an enemy hits an ally adjacent to it with a melee attack",
    ),
)
def m5827a3(c: Cast) -> None:
    c.redirect(to=c.me)


# ==========================================================================
# m6425
# ==========================================================================


@power(
    "m6425a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m6425a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m6425a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m6425a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6425a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes a melee or a ranged attack against an ally adjacent to it",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: _redirect_gate(w, m, ev, "melee", "ranged"),
        "an enemy makes a melee or a ranged attack against an ally adjacent to it",
    ),
)
def m6425a2(c: Cast) -> None:
    c.redirect(to=c.me)


# ==========================================================================
# m6431
# ==========================================================================


@power("m6431a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6431a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m6431a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m6431a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if has_combat_advantage(c.world, c.me, c.target):
            c.flat(2)


@power(
    "m6431a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6431a2(c: Cast) -> None:
    _mobile_attack(c, 3, shifting=True)


# ==========================================================================
# m6676
# ==========================================================================


@power(
    "m6676a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m6676a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if any(is_(c.world, c.target, cnd) for cnd in _PINNED_FOUR):
            c.flat(3)


@power(
    "m6676a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack misses it",
    on=Trigger(Miss, targets_me, "an attack misses it"),
)
def m6676a1(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))
