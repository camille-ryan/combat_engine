"""Monster abilities, level 9, lurkers.

Fifteen stat blocks, fifty-three rows; four of the fifteen (`m173`, `m2938`,
`m419`, `m428`) print no abilities at all and have nothing to decorate.

Conventions, inherited from the level 1-8 lurker sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a printed range band like "5/10" takes the short number; a card with no
  printed range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* "Target: a creature grabbed by it" is the target's own state, not the
  chooser's business -- `Target` filters side, count and size and not what
  a creature is suffering, so `_restricted_to` (level_03) is reused and the
  use is marked `dropped=("Target.relation",)` -- "grabbed **by it**" is a
  relation to the caster and not a condition anybody carries;
* a printed escape DC has nowhere to go -- every grab here is
  `dropped=("c.grab(dc=)",)`;
* a blow of two damage types rolled once keeps the first in the header and
  carries the rest as a keyword, marked `dropped=("Damage(dtypes=)",)`;
* "alters its physical form... retains its statistics" is a disguise with
  no mechanical change at all, declared `out_of_combat=True`.

Two new local helpers: `_dominated_by_me` asks the relation a dominate
condition wires up on its own, and `_kin_adjacent_count` is `_kin_count`
(level-8) read the other way -- how many of this exact block are next to
*the target* rather than next to an ally.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.lurkers_sa import _recharge_when_using
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    DamageApplied,
    DamageRolled,
    Escaped,
    Hit,
    MoveEnd,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import has_combat_advantage, unseen_by
from combat_engine.engine.triggers import Trigger, by_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------




def _dominated_by_me(c: Cast, victim: int) -> bool:
    return c.me in c.world.relations.targets(Relation.DOMINATED_BY, victim)


def _kin_adjacent_count(c: Cast, victim: int, ref: str) -> int:
    return sum(
        1
        for a in c.within(1, of=victim, side="any")
        if (ident := c.world.get(a, Ident)) is not None and ident.ref == ref
    )


# ==========================================================================
# m1083
# ==========================================================================


@power(
    "m1083a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.POISON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6),
    dropped=("Damage(dtypes=)",),
)
def m1083a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(2, dtype=DamageType.POISON)


@power(
    "m1083a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1083a1(c: Cast) -> None:
    me = c.me
    c.gains_advantage(
        lambda ctx: ctx.get("target") is not None and unseen_by(c.world, ctx["target"], me),
        until=When.ENCOUNTER, on=me,
    )


@power(
    "m1083a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1083a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "m1083a0",
    )


@power(
    "m1083a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1083a3(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.penalty("attack", 2, on=me, until=When.SONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} glare")


_M1083_RESTRAINING = frozenset({Condition.IMMOBILIZED, Condition.RESTRAINED})


@power(
    "m1083a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1083a4(c: Cast) -> None:
    me = c.me
    c.bonus("escape", 2, kind="racial", on=me, until=When.ENCOUNTER)
    c.bonus(
        "save", 2, kind="racial", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(set(ctx.get("conditions", ())) & _M1083_RESTRAINING),
    )


# ==========================================================================
# m1988
# ==========================================================================


@power(
    "m1988a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 6, dtype=DamageType.NECROTIC),
)
def m1988a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1988a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION, Keyword.WEAPON],
)
def m1988a1(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m1988a0", on=victim)
    c.teleport(5)
    c.insubstantial(until=When.SONT)
    c.phasing(until=When.SONT)


@power(
    "m1988a2",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
)
def m1988a2(c: Cast) -> None:
    victim = c.target
    me = c.me
    if not c.strike() or victim is None:
        return

    def punish(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target == me:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(AttackDeclared, punish, until=When.SAVE_ENDS, on=me, label=c.ref)


# ==========================================================================
# m1995
# ==========================================================================


@power(
    "m1995a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1995a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1995a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1995a1(c: Cast) -> None:
    def beside(ctx: dict) -> bool:
        victim = ctx.get("target")
        return victim is not None and _kin_adjacent_count(c, victim, "m1995") >= 2

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=beside)


@power(
    "m1995a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d4", 10),
)
def m1995a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1995_HURT = "the m1995 takes damage"


@power(
    "m1995a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=Target(side="ally", label="one allied m1995 in the burst"),
    trigger=_M1995_HURT,
    on=Trigger(DamageRolled, targets_me, _M1995_HURT),
)
def m1995a3(c: Cast) -> None:
    mate = next(
        (a for a in c.within(3, side="ally") if (i := c.world.get(a, Ident)) and i.ref == "m1995"),
        None,
    )
    if mate is not None:
        c.redirect(to=mate)


# ==========================================================================
# m2103
# ==========================================================================


@power(
    "m2103a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d12", 6),
)
def m2103a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2103a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d12", 6),
    dropped=("c.grab(dc=)",),
)
def m2103a1(c: Cast) -> None:
    me = c.me
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    c.ongoing(10)
    if not c.grabbing(of=me):
        c.grab()
    for d in (AC, "fort", "ref", "will"):
        c.bonus(d, 4, on=me, until=When.ENCOUNTER, when=lambda _ctx: bool(c.grabbing(of=me)))


@power(
    "m2103a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2103a2(c: Cast) -> None:
    me = c.me
    c.bonus(
        "damage", 0, dice="1d8", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and not ctx.get("ranged"),
    )
    c.bonus(
        "damage", 0, dice="1d8", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m2103a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:stealth",),
)
def m2103a3(c: Cast) -> None:
    """The Stealth bonus is narrative -- nothing on a board rolls it. The
    ready-and-ambush half plays: it fires once, on the first enemy to move
    adjacent, which is what a readied action is for -- one shot, not a
    standing watch."""
    me = c.me
    c.hide(until=When.ENCOUNTER)
    fired = False

    def ambush(ev: MoveEnd) -> None:
        nonlocal fired
        if fired or ev.actor == me:
            return
        if ev.actor in c.enemies() and c.distance(ev.actor) <= 1:
            fired = True
            c.use_power("m2103a0", on=ev.actor)

    c.watch(MoveEnd, ambush, until=When.ENCOUNTER, on=me, label=f"{c.ref} ambush")


# ==========================================================================
# m2235
# ==========================================================================


@power(
    "m2235a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m2235a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2235a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m2235a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m2235a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.move(ends_on=)",),
)
def m2235a2(c: Cast) -> None:
    """Landing only on the ground or a surface it can cling to is a
    constraint on where the move may end; `c.move` takes no such
    restriction, so the fly itself is written and the landing rule is not."""
    c.move(10, at="fly")


# ==========================================================================
# m2619
# ==========================================================================


def _medium_or_smaller(c: Cast, who: int) -> bool:
    from combat_engine.engine import Size

    order = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE, Size.HUGE, Size.GARGANTUAN)
    return order.index(c.size_of(who)) <= order.index(Size.MEDIUM)


@power(
    "m2619a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 3),
)
def m2619a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2619a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    dropped=("When.ESCAPE",),
)
def m2619a1(c: Cast) -> None:
    """No printed damage number at all -- the Effect is the grab, the pull
    and the ongoing burn, and the attack roll only gates whether they land.

    "Medium or smaller" is **not** a gap: `Target(max_size=)` says it, so the
    marker was re-aimed off the target line entirely. What is missing is the
    clock: the daze and the burn run "until it escapes the grab" and `When`
    has no escape-tied member, so both are hung on `When.ENCOUNTER` instead
    and `When.ESCAPE` is the named gap."""
    victim = _restricted_to(c, 1, lambda f: _medium_or_smaller(c, f))
    if victim is None:
        return
    landed = (
        True
        if has_combat_advantage(c.world, c.me, victim)
        else c.strike(on=victim)
    )
    if not landed:
        return
    c.grab(on=victim)
    c.dazed(on=victim, until=When.ENCOUNTER)
    c.ongoing(10, on=victim)


_M2619_ESCAPED = "a creature escapes the m2619's grab"


def _escaped_my_grab(world: World, me: int, ev: Escaped) -> bool:
    return ev.holder == me and bool(ev.success)


@power(
    "m2619a2",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2619_ESCAPED,
    on=Trigger(Escaped, _escaped_my_grab, _M2619_ESCAPED),
)
def m2619a2(c: Cast) -> None:
    victim = getattr(c.trigger, "actor", None)
    if victim is not None:
        c.use_power("m2619a0", on=victim)


@power(
    "m2619a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2619a3(c: Cast) -> None:
    c.shift(3)
    chosen = next((f for f in c.within(6, side="enemy")), None)
    if chosen is not None:
        c.grants_advantage(on=chosen, to="me", until=When.EONT)


@power(
    "m2619a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2619a4(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(6)


# ==========================================================================
# m3299
# ==========================================================================


@power(
    "m3299a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m3299a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3299a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m3299a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3299a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3299a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m3299a0", on=victim)
        c.use_power("m3299a0", on=victim, again=True)


@power(
    "m3299a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m3299a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(until=When.EONT)


@power(
    "m3299a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, within=12),
    target=Target(side="any", everyone=True, label="creatures in the burst"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d8", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3299a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m3299a5",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m3299a5(c: Cast) -> None:
    me = c.me
    ring = c.zone(c.area(), blocks_sight=True, until=When.EONT, label=c.ref)

    def blind(who: int) -> None:
        if who != me:
            c.blinded(on=who, until=When.EONT)

    for who in c.world.zones.occupants(ring):
        blind(who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            blind(ev.actor)

    def left(ev: ZoneExited) -> None:
        if ev.zone == ring and ev.actor != me:
            c.cure(Condition.BLINDED, on=ev.actor)

    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=me, label=f"{c.ref} out")


@power(
    "m3299a6",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:stealth",),
)
def m3299a6(c: Cast) -> None:
    """The Stealth bonus is narrative -- nothing on a board rolls a Stealth
    check to notice it, so the circumstance has no combat reading."""
    c.insubstantial(until=When.EONT)
    c.phasing(until=When.EONT)
    c.vulnerable(5, DamageType.RADIANT, until=When.EONT)


# ==========================================================================
# m4355
# ==========================================================================


@power(
    "m4355a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 5, dtype=DamageType.FIRE),
)
def m4355a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(on=c.target, to="team", until=When.EONT)


@power(
    "m4355a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4355a1(c: Cast) -> None:
    _recharge_when_using(c, "m4355a2")
    c.no_provoke(on=c.me, until=When.EOT)
    for victim in c.overrun():
        if c.attack(c.world.scaling.trim(12, c.level), REF, on=victim):
            c.damage("2d8", 5, dtype=DamageType.FIRE, on=victim)
            c.grants_advantage(on=victim, to="team", until=When.EONT)


@power(
    "m4355a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.form(return_within=)",),
)
def m4355a2(c: Cast) -> None:
    """Cannot attack or be attacked while in steam form plays; resuming
    only within 8 squares of where it changed, and that turn's attacks
    blinding instead of granting advantage, have no counterpart -- nothing
    remembers a past square against a later one, or swaps what a blow
    causes for a single turn."""
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    c.hide(until=When.ENCOUNTER)
    c.insubstantial(until=When.ENCOUNTER)


# ==========================================================================
# m4371
# ==========================================================================


@power(
    "m4371a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m4371a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4371a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m4371a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4371a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
)
def m4371a2(c: Cast) -> None:
    for _ in range(2):
        c.basic(on=c.target)


@power(
    "m4371a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m4371a3(c: Cast) -> None:
    me = c.me

    def shadowstruck(ev: Hit) -> None:
        if ev.attacker == me and c.is_hidden(from_=ev.target):
            c.ongoing(15, DamageType.PSYCHIC, on=ev.target)

    c.watch(Hit, shadowstruck, until=When.ENCOUNTER, on=me, label=f"{c.ref} shadow")


@power(
    "m4371a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4371a4(c: Cast) -> None:
    me = c.me
    seen = [f for f in c.enemies() if c.can_see(f)][:2]
    for foe in seen:
        c.invisible(to=foe, on=me, until=When.EONT)
    c.insubstantial(until=When.EONT)
    c.conceal(on=me, until=When.EONT)


_M4371_ROLLED = "m4371 makes an attack roll"


@power(
    "m4371a5",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4371_ROLLED,
    on=Trigger(AttackRolled, by_me, _M4371_ROLLED),
)
def m4371a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m4371a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4371a6(c: Cast) -> None:
    c.ignores_difficult(kind="shift", on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5132
# ==========================================================================


@power(
    "m5132a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5132a0(c: Cast) -> None:
    me = c.me

    def dominated(ctx: dict) -> bool:
        victim = ctx.get("target")
        return c.bloodied(me) and victim is not None and _dominated_by_me(c, victim)

    c.bonus("attack", 5, on=me, until=When.ENCOUNTER, when=dominated)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=dominated)


@power(
    "m5132a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 4),
    requires=lambda world, eid: not world.relations.targets(Relation.GRABBED_BY, eid),
    requires_text="the m5132 must not have a creature grabbed",
)
def m5132a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if not c.grabbing(of=c.me):
            c.grab()


@power(
    "m5132a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 8),
    dropped=("Target.relation",),
)
def m5132a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(on=victim, until=When.EONT)


@power(
    "m5132a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=12),
    dropped=("c.leaves_play()",),
)
def m5132a3(c: Cast) -> None:
    """Domination plays; the m5132 being removed from play and steering the
    target's own move and standard actions from inside it has no
    counterpart -- nothing in `Cast` takes a creature off the board and
    back on at the end of somebody else's save."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m5132a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5132a4(c: Cast) -> None:
    """Retains its own statistics in the new form -- a disguise with no
    mechanical change, like every other polymorph-to-a-copy in this file."""


@power(
    "m5132a5",
    level=9,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="the m5132 takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me
        and ev.dtype in (
            DamageType.ACID, DamageType.COLD, DamageType.FIRE,
            DamageType.LIGHTNING, DamageType.THUNDER,
        ),
        "the m5132 takes acid, cold, fire, lightning, or thunder damage",
    ),
)
def m5132a5(c: Cast) -> None:
    hit_type = getattr(c.trigger, "dtype", None)
    if hit_type is not None:
        c.resist(5, hit_type, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5514
# ==========================================================================


@power(
    "m5514a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6),
)
def m5514a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if bool(getattr(c.result, "advantage", False)):
            c.ongoing(5, DamageType.POISON)


@power(
    "m5514a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d4", 6),
)
def m5514a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5514a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5514a2(c: Cast) -> None:
    c.shift(3)
    victims = [f for f in c.enemies() if c.distance(f) <= 1][:2]
    for victim in victims:
        c.use_power("m5514a0", on=victim)


@power(
    "m5514a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=Target(side="enemy", everyone=True, label="enemies in the blast"),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m5514a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m5514a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5514a4(c: Cast) -> None:
    """Retains its own statistics -- a disguise, same shape as `m5132a4`."""


@power(
    "m5514a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5514a5(c: Cast) -> None:
    chosen = next((f for f in c.enemies() if c.can_see(f)), None)
    if chosen is not None:
        c.grants_advantage(on=chosen, to="me", until=When.EONT)
