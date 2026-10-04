"""Monster abilities, level 7: the blocks that print no role.

Two stat blocks, thirteen rows -- the handful of level-7 role-less blocks;
everything else at this level is artillery, lurker, minion, skirmisher, or
the brute/soldier/controller sweeps landed elsewhere. As at levels 5 and 6,
a role-less block here reads like a companion's card rather than an
encounter monster, which is a fact about the card and not an error.

Conventions, inherited from the sweeps below this level:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as the card prints it, and the damage line goes in the header as
  data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims;
* a printed range band like "10/20" takes the short number; no printed
  range at all is melee 1;
* a close burst naming no target set takes enemies, except where the card
  names allies instead -- both bursts in this file do: one is the caster
  swapping places with an ally, the other is a single ally singled out of
  a burst rather than everyone in it;
* an "Effect:" line with no "+N vs X" rolls no attack at all, so no `Attack=`
  header is invented for one;
* `c.spend_surge` is an ally spending its own surge -- this file's monster
  never spends its own.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    When,
    World,
    power,
)
from combat_engine.engine.events import Hit
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import enemies
from combat_engine.engine.triggers import Trigger

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_ALL_DEFENCES = (AC, FORT, REF, WILL)


# ==========================================================================
# m5605
# ==========================================================================


@power(
    "m5605a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m5605a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5605a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5605a1(c: Cast) -> None:
    """No attack roll at all -- the card prints only an Effect line. The
    caster's own 13 damage is unconditional, not a strike it can miss."""
    mate = c.target
    if mate is None:
        return
    c.flat(13, on=c.me)
    c.heal(26, on=mate)


@power(
    "m5605a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
)
def m5605a2(c: Cast) -> None:
    """"The next ally who hits the target... regains 4 hit points" is one
    reward, for the first ally's hit only -- `once=True` and the watch's own
    end at `When.EONT` match the printed window."""
    victim = c.target
    if not c.strike():
        return
    for d in _ALL_DEFENCES:
        c.penalty(d, 2, on=victim, until=When.EONT)

    def rewarded(ev: Hit) -> None:
        if ev.target != victim or ev.attacker not in c.allies():
            return
        c.heal(4, on=ev.attacker)

    c.watch(Hit, rewarded, until=When.EONT, on=c.me, once=True, label=c.ref)


@power(
    "m5605a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=11),
)
def m5605a3(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)
        for d in _ALL_DEFENCES:
            c.penalty(d, 2, until=When.EONT)


@power(
    "m5605a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 7, dtype=DamageType.RADIANT),
)
def m5605a4(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    ally = next((a for a in c.allies() if c.can_see(a)), None)
    if ally is None:
        return
    pick = c.choose(["temporary hit points", "a saving throw"], c.ref)
    if pick == "temporary hit points":
        c.temp_hp(5, on=ally)
    else:
        c.save(on=ally)


@power(
    "m5605a5",
    level=7,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5605a5(c: Cast) -> None:
    c.spend_surge(on=c.target)


# ==========================================================================
# m5607
# ==========================================================================


@power(
    "m5607a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:diplomacy",),
)
def m5607a0(c: Cast) -> None:
    """The Diplomacy bonus itself is narrative -- nothing on a board rolls
    Diplomacy. The aura's radius is mechanical on its own and is declared
    regardless, so the row is not empty."""
    c.aura(10, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)


@power(
    "m5607a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 8),
)
def m5607a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5607a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 9),
)
def m5607a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5607a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m5607a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5607a4",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5607a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m5607a5",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=ONE_ALLY,
)
def m5607a5(c: Cast) -> None:
    """"m5607 and one ally" swap places -- the burst singles out one ally
    in reach rather than moving everyone it catches."""
    mate = c.target
    if mate is not None:
        c.swap(mate)


_M5607_ADVANTAGE_HIT = "it hits an enemy that is granting it combat advantage"


def _m5607_advantage_hit(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.attacker == me
        and ev.target in enemies(world, me)
        and bool(getattr(ev.result, "advantage", False))
    )


@power(
    "m5607a6",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5607_ADVANTAGE_HIT,
    on=Trigger(Hit, _m5607_advantage_hit, _M5607_ADVANTAGE_HIT),
)
def m5607a6(c: Cast) -> None:
    """"(No Action)" beats the header's own "free" -- the parenthetical is
    the actual parsed sentence. "Did this attack have combat advantage?" is
    `ev.result.advantage`, read off the `Hit` rather than asked again."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.flat(c.roll("1d6"), on=victim)
