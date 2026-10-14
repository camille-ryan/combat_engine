"""Monster abilities, level 10, lurkers.

Nineteen stat blocks, seventy-three rows; six of the nineteen (`m130`,
`m1580`, `m3081`, `m326`, `m4860`, `m4990`) print no abilities at all and
have nothing to decorate.

Conventions, inherited from the level 1-9 lurker sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a printed range band like "5/10" takes the short number; a card with no
  printed range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**;
* "Target: a creature grabbed by it" is the target line's own business:
  `Target` carries `relation`, `conditions` and `bloodied`, so the
  restriction goes in the header and the body takes `c.target`. Nothing
  here calls `_restricted_to` any more, but five later files import it
  *from here* rather than from level 3, so the line stays with a `noqa`;
* a printed escape DC that is actually on the card is
  `dropped=("c.grab(dc=)",)`; several blocks here print the grab with no
  DC at all, and those take no marker;
* "alters its physical form... retains its statistics" is a disguise with
  no mechanical change, declared `out_of_combat=True`;
* `m6373` carries both the lurker and minion tags on its own card -- it is
  written here because that is where the brief for this file drew it, and
  its one attack still deals `Damage("", n, kind=MINION)`.

One block (`m3295`) spotlights a target with a minor action and three other
rows read that spotlight back; `_m3295_tag`/`_m3295_tagged` hold it as a
same-labelled `Effect` per victim rather than inventing a relation, since
nothing elsewhere in the tree needs "is this creature the one a minor
action pointed at" to survive past one `EONT`.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.lurkers_sa import _twice
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to  # noqa: F401
from combat_engine.content.monsters.level_08.brutes import _aura
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
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
    Effect,
    Health,
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
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import enemies, hidden_from, unseen_by
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------




_M3295_TAG = "m3295a1"


def _m3295_tag(c: Cast, who: int) -> None:
    c.effect(_M3295_TAG, on=who, until=When.EONT)


def _m3295_tagged(c: Cast, who: int) -> bool:
    return any(eff.label == _M3295_TAG for eff in c.world.effects.of(who))


def _m3295_shield(c: Cast, who: int) -> None:
    me = c.me
    c.bonus(AC, 5, on=me, until=When.EONT, when=lambda ctx, who=who: ctx.get("attacker") == who)
    c.bonus(REF, 5, on=me, until=When.EONT, when=lambda ctx, who=who: ctx.get("attacker") == who)


# ==========================================================================
# m115875
# ==========================================================================


@power(
    "m115875a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5),
    dropped=("c.host(decoy=)",),
)
def m115875a0(c: Cast) -> None:
    """The decoy tentacle -- a second, attackable body standing in for the
    real one, taking no damage itself and ending the grab if struck -- has
    no counterpart: nothing in the engine puts a second, independently
    targetable body on a square. The grab and the resist play."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    c.grab(dc=26)
    # `source` is the damage context's name for who dealt it; `attacker`
    # is the *attack* context's and was never in this one, so the resist
    # applied to nobody. #380.
    c.resist(20, on=c.me, until=When.EONT, when=lambda ctx: ctx.get("source") == victim)


@power(
    "m115875a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=Target(
        "enemy", 1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=REF, printed=13),
    damage=Damage("4d10", 5, half_on_miss=True),
)
def m115875a1(c: Cast) -> None:
    """The Effect pulls before anything is rolled, and the grab ends on both
    branches -- so the release is outside the hit test, not inside it."""
    victim = c.target
    if victim is None:
        return
    c.pull(10)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    for hold in list(c.world.effects.of(victim)):
        if hold.label == "m115875a0":
            c.world.effects.end(hold, "the grab ends")


# ==========================================================================
# m1193
# ==========================================================================


@power(
    "m1193a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m1193a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1193a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC),
)
def m1193a1(c: Cast) -> None:
    if c.strike():
        dealt = c.hit()
        c.heal(dealt, on=c.me)


@power(
    "m1193a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1193a2(c: Cast) -> None:
    """"Even magical light" reaches further than a physical source -- only
    the scenery half is one, so a conjured light with nothing on the board
    standing for it cannot be found or put out."""
    for fire in c.scenery("fire", within=10):
        c.douse(on=fire)


@power(
    "m1193a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1193a3(c: Cast) -> None:
    c.conceal(
        on=c.me, total=True, until=When.ENCOUNTER,
        when=lambda _ctx: c.terrain("dim light") or c.terrain("darkness"),
    )


@power(
    "m1193a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1193a4(c: Cast) -> None:
    me = c.me

    def hidden_from_me(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and unseen_by(c.world, who, me)

    c.bonus("damage", 0, dice="2d6", on=me, until=When.ENCOUNTER, when=hidden_from_me)

    def surge_lost(ev: Hit) -> None:
        if ev.attacker == me and unseen_by(c.world, ev.target, me):
            c.spend_surge(on=ev.target)

    c.watch(Hit, surge_lost, until=When.ENCOUNTER, on=me, label=f"{c.ref} drain")


# ==========================================================================
# m1419
# ==========================================================================


@power(
    "m1419a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m1419a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1419a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 4),
)
def m1419a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1419a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1419a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m1419a0", on=victim)
        c.use_power("m1419a1", on=victim)


_M1419_SNIPED = "an enemy attacks the m1419 with a ranged attack"


@power(
    "m1419a3",
    level=10,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 2),
    trigger=_M1419_SNIPED,
    on=Trigger(AttackDeclared, both(targets_me, by_ranged), _M1419_SNIPED),
)
def m1419a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.blinded(on=foe, until=When.EONT)


@power(
    "m1419a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(10),
    target=Target(side="any", everyone=True, label="creatures in the blast"),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d8", 3, kind=LIMITED),
)
def m1419a4(c: Cast) -> None:
    me = c.me
    if c.first:
        ring = c.zone(c.area(), until=When.EONT, blocks_sight=True, label=c.ref)

        def scorches(who: int) -> bool:
            return who != me and (who in c.world.zones.occupants(ring) or c.distance(who) <= 1)

        def burn(ev: TurnStart) -> None:
            if not ev.ghost and scorches(ev.actor):
                c.flat(5, on=ev.actor)

        c.watch(TurnStart, burn, until=When.EONT, on=me, label=f"{c.ref} sand")
    if c.strike():
        c.hit()


@power(
    "m1419a5",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when first bloodied",
    on=Trigger(Bloodied, about_me, "when first bloodied"),
)
def m1419a5(c: Cast) -> None:
    c.restore_use("m1419a4")
    c.use_power("m1419a4", again=True)


@power(
    "m1419a6",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m1419a6(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m1419a7",
    level=10,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1419a7(c: Cast) -> None:
    for victim in c.overrun():
        c.flat(c.roll("1d8") + 6, on=victim)
        c.blinded(on=victim, until=When.SAVE_ENDS)


@power(
    "m1419a8",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1419a8(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m2107
# ==========================================================================


@power(
    "m2107a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 1),
)
def m2107a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.grab()


@power(
    "m2107a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2107a1(c: Cast) -> None:
    """"Gold coins or similar material" cannot be told apart from any other
    scenery on the board the audit runs against, so this reads for any
    scenery sharing the m2107's own square."""
    c.conceal(
        on=c.me, total=True, until=When.ENCOUNTER,
        when=lambda _ctx: bool(c.scenery(within=0)),
    )


@power(
    "m2107a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2107a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m2508
# ==========================================================================


@power(
    "m2508a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m2508a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2508a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 5),
)
def m2508a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2508_DOWN = "the m2508 is reduced to 0 hit points"


@power(
    "m2508a2",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    trigger=_M2508_DOWN,
    on=Trigger(Dropped, about_me, _M2508_DOWN),
)
def m2508a2(c: Cast) -> None:
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m2508a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, within=10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(blocks_sight_except=)",),
)
def m2508a3(c: Cast) -> None:
    """Darkvision seeing through the zone has no counterpart -- `c.zone`
    blocks sight for everyone a watcher asks about, with no exemption."""
    c.zone(c.area(), blocks_sight=True, until=When.EONT, sustain=MINOR, label=c.ref)


@power(
    "m2508a4",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="requires scimitar",
    dropped=("etl.monster.weapon()",),
)
def m2508a4(c: Cast) -> None:
    """The weapon-group gate cannot be asked -- a monster's own gear is
    never populated with one -- so the row plays unconditionally."""
    c.maximise(on=c.me, until=When.EONT, critical=True)


@power(
    "m2508a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2508a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m2508a6",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2508a6(c: Cast) -> None:
    me = c.me
    c.bonus(AC, 4, on=me, until=When.EOT, when=lambda ctx: bool(ctx.get("opportunity")))
    c.move(4)
    for foe in c.within(1, side="enemy"):
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power(
    "m2508a7",
    level=10,
    usage=Usage.RECHARGE,
    recharge=3,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m2508a7(c: Cast) -> None:
    c.invisible(until=When.EONT)


# ==========================================================================
# m3295
# ==========================================================================


@power(
    "m3295a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m3295a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m3295a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    narrative=("skill:insight",),
)
def m3295a1(c: Cast) -> None:
    """The Insight half is narrative -- nothing on a board rolls a check
    against it. The AC and Reflex shielding plays."""
    victim = c.target
    if victim is None:
        return
    _m3295_tag(c, victim)
    _m3295_shield(c, victim)


@power(
    "m3295a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
)
def m3295a2(c: Cast) -> None:
    for foe in c.within(3, side="enemy"):
        _m3295_tag(c, foe)
        _m3295_shield(c, foe)


@power(
    "m3295a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies under m3295a1"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
    dropped=("Target.affected_by",),
)
def m3295a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not _m3295_tagged(c, victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.PSYCHIC, on=victim)


@power(
    "m3295a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3295a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None and _m3295_tagged(c, ctx["target"]),
    )


@power(
    "m3295a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.damage_disadvantage(against=)",),
)
def m3295a5(c: Cast) -> None:
    """Forcing *another* creature's attack roll into disadvantage has no
    counterpart -- `c.gains_advantage` and `c.damage_disadvantage` are both
    the caster's own, and nothing hands the two-rolls-take-lower rule to an
    attacker aiming at a defence of the caster's choosing."""


# ==========================================================================
# m3315
# ==========================================================================


@power(
    "m3315a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 7),
)
def m3315a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3315a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m3315a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3315a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3315a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3315a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3315a3(c: Cast) -> None:
    me = c.me
    held = c.conceal(on=me, total=True, until=When.ENCOUNTER)
    if held is None:
        return

    def landed(ev: Hit) -> None:
        if ev.attacker == me:
            c.world.effects.end(held, "it hit")

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} veil")


@power(
    "m3315a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3315a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m3315a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3315a5(c: Cast) -> None:
    """`c.unhide` is never called by the engine on its own, so a miss while
    hidden already leaves the m3315 hidden -- there is nothing this row
    needs to do that is not already true."""


@power(
    "m3315a6",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="m3315 makes an attack roll",
    on=Trigger(AttackRolled, by_me, "m3315 makes an attack roll"),
)
def m3315a6(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m3315a7",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3315a7(c: Cast) -> None:
    c.ignores_difficult(kind="shift", on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3997
# ==========================================================================


@power(
    "m3997a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 3),
)
def m3997a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3997a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d6", 3),
)
def m3997a1(c: Cast) -> None:
    """Domination, and a body kept on its feet until the hold breaks.

    **"Until it saves against the dominated effect" needed no event id.**
    `c.dominate` hands back the `Effect` it laid, and an `Effect` carries
    `on_end` -- so the clause is hung on *that* hold's own ending, which is
    how `m6113a3` and `m6070a3` tie one clause to one effect. The old
    marker wanted `EffectExpired.effect_id` to tell one expiry from
    another; holding the effect means never having to ask.

    **And `c.dominate` rather than the bare condition, which is a second
    correction.** `Relation.DOMINATED_BY` has fifteen readers and
    `relations.IMPLIES` maps relation to condition one way only, so the
    condition alone filed none of them -- including
    `_dominated_by_any_m3997` just below, this block's own gate on
    `m3997a2`, which was therefore false after every use of this row.

    **The immunity is laid before the blow**, because `c.immune` refuses
    what arrives and does not strip what is already there -- a creature
    taken to 0 by this very attack would otherwise be dying before the
    line could be written. It is lifted again when the blow turns out not
    to have dropped it, so nothing is held that the card does not grant."""
    victim = c.target
    if victim is None or not c.strike():
        return
    spared = c.immune(Condition.DYING, on=victim, until=When.ENCOUNTER)
    c.hit()
    held = c.dominate(on=victim, until=When.SAVE_ENDS)
    if spared is None:
        return
    body = c.world.get(victim, Health)
    if held is None or body is None or body.hp > 0:
        c.world.effects.end(spared, "the blow did not drop it")
        return

    def dies_properly() -> None:
        if not spared.ended:
            c.world.effects.end(spared, "the target saved")

    held.on_end.append(dies_properly)


def _dominated_by_any_m3997(c: Cast, who: int) -> bool:
    for src in c.world.relations.targets(Relation.DOMINATED_BY, who):
        ident = c.world.get(src, Ident)
        if ident is not None and ident.ref == "m3997":
            return True
    return False


@power(
    "m3997a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(5),
    target=Target(side="enemy", everyone=True, label="enemies in the blast"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3997a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and _dominated_by_any_m3997(c, victim):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


_M3997_TARGETED = "m3997 is targeted by a melee or ranged attack"


def _melee_or_ranged(world: World, me: int, ev: AttackDeclared) -> bool:
    return by_melee(world, me, ev) or by_ranged(world, me, ev)


@power(
    "m3997a3",
    level=10,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3997_TARGETED,
    on=Trigger(AttackDeclared, both(targets_me, _melee_or_ranged), _M3997_TARGETED),
)
def m3997a3(c: Cast) -> None:
    me = c.me
    shield = next(
        (v for v in c.world.relations.targets(Relation.DOMINATED_BY, me) if c.adjacent(v)),
        None,
    )
    if shield is not None:
        c.redirect(to=shield)


# ==========================================================================
# m5188
# ==========================================================================

_M5188_DARK = "m5188 dark"


def _m5188_lit(world: World, eid: int) -> bool:
    return not any(eff.label == _M5188_DARK for eff in world.effects.of(eid))


@power(
    "m5188a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.RADIANT),
    requires=_m5188_lit,
    requires_text="the m5188 must be illuminated",
)
def m5188a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5188a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(3),
    target=Target(side="enemy", label="one bloodied creature", bloodied=True),
    keywords=[Keyword.HEALING, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
    requires=_m5188_lit,
    requires_text="the m5188 must be illuminated",
)
def m5188a1(c: Cast) -> None:
    """The illumination Requirement is about the creature itself and stays; it
    is the bloodied half of the gate that the target line now carries."""
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
        c.heal(14, on=c.me)


@power(
    "m5188a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(20),
    target=Target(
        side="enemy", label="one nonbloodied creature in the burst", bloodied=False,
    ),
    attack=Attack(vs=WILL, printed=13),
    requires=_m5188_lit,
    requires_text="the m5188 must be illuminated",
)
def m5188a2(c: Cast) -> None:
    """"Nonbloodied" is `bloodied=False` and not the absence of the field --
    the tri-state is what keeps this row from becoming its own opposite."""
    if c.strike():
        c.pull(3)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5188a3",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5188a3(c: Cast) -> None:
    me = c.me
    held = next((eff for eff in c.world.effects.of(me) if eff.label == _M5188_DARK), None)
    if held is not None:
        c.world.effects.end(held, "relit")
        return
    dark = c.effect(_M5188_DARK, on=me, until=When.ENCOUNTER)
    if dark is None:
        return
    c.conceal(on=me, until=When.ENCOUNTER, when=lambda _ctx: not _m5188_lit(c.world, me))
    c.hide(until=When.ENCOUNTER)


_M5188_MISSED = "an attack misses the m5188"


@power(
    "m5188a4",
    level=10,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5188_MISSED,
    on=Trigger(Miss, targets_me, _M5188_MISSED),
)
def m5188a4(c: Cast) -> None:
    me = c.me
    if not any(eff.label == _M5188_DARK for eff in c.world.effects.of(me)):
        c.effect(_M5188_DARK, on=me, until=When.ENCOUNTER)
    c.teleport(5)


_M5188_SLAIN = "the m5188 drops to 0 hit points and is killed"


@power(
    "m5188a5",
    level=10,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5188_SLAIN,
    on=Trigger(Dropped, about_me, _M5188_SLAIN),
)
def m5188a5(c: Cast) -> None:
    """Stays up and fights on, and takes a type word for as long as it does.

    Staying up is a heal back off 0 with the dying condition refused.

    **The type word is `c.set_origin`, not `Ident`.** `Ident` carries a
    ref, which is why the old marker asked for a keyword list on it -- but
    `query.kinds_of` reads a stat block's own type line *plus anything
    `c.set_origin` has written*, and that union is the one set `c.is_kind`
    and `Target.kinds` both answer from. So the word is held as a labelled
    effect on the same clock as the rest of the clause, which is what "for
    the rest of that time" means, and a target line reading "each undead
    creature in the burst" now reaches this one."""
    if getattr(c.trigger, "dead", False):
        c.heal(1, on=c.me)
        c.immune(Condition.DYING, on=c.me, until=When.EONT)
        c.set_origin("undead", on=c.me, until=When.EONT)


# ==========================================================================
# m5817
# ==========================================================================

_M5817_HEAD = "m5817 head"

#: "On that turn it can use that power and bite with a single standard
#: action" -- armed by `m5817a5` only when the hiding condition held, and
#: read by `m5817a4`, which is the standard action the pair is bought with.
_M5817_PAIRED = "m5817 paired"


def _m5817_in_head_form(world: World, eid: int) -> bool:
    return any(eff.label == _M5817_HEAD for eff in world.effects.of(eid))


def _m5817_in_maiden_form(world: World, eid: int) -> bool:
    return not _m5817_in_head_form(world, eid)


def _m5817_hidden_from_all(world: World, eid: int) -> bool:
    """"If it starts its next turn hidden from all enemies", which is both
    the recharge condition on `m5817a4` and the gate on the paired attack.

    A state, not a moment, which is why it is `recharge_while=` and not a
    `Trigger`: hiding ends on a move, on an attack, on somebody gaining
    truesight, and watching every route to re-ask is the fragile way round.
    `recharge_while=` is asked at the start of this creature's turn, beside
    the die, which is the clause word for word.

    `query.hidden_from` rather than the relation, because a watcher who
    sees through the hiding is not one it is hidden from. No enemies at all
    is false: a creature alone on the board is not hiding from anybody.
    """
    foes = enemies(world, eid)
    return bool(foes) and set(foes) <= hidden_from(world, eid)


def _m5817_paired(world: World, eid: int) -> bool:
    return any(eff.label == _M5817_PAIRED for eff in world.effects.of(eid))


@power(
    "m5817a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 4),
    requires=_m5817_in_maiden_form,
    requires_text="the m5817 must be in maiden form",
)
def m5817a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5817a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=Target(side="any", everyone=True, label="creatures in the burst"),
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
    requires=_m5817_in_maiden_form,
    requires_text="the m5817 must be in maiden form",
)
def m5817a1(c: Cast) -> None:
    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m5817a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("4d6", 6, dtype=DamageType.PSYCHIC),
    requires=_m5817_in_maiden_form,
    requires_text="the m5817 must be in maiden form",
)
def m5817a2(c: Cast) -> None:
    if c.first:
        c.effect(_M5817_HEAD, on=c.me, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.dazed(until=When.EOTNT)


@power(
    "m5817a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 3),
    requires=_m5817_in_head_form,
    requires_text="the m5817 must be in head form",
)
def m5817a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5817a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d12", 8, dtype=DamageType.NECROTIC, kind=LIMITED),
    requires=_m5817_in_head_form,
    requires_text="the m5817 must be in head form",
    recharge_while=_m5817_hidden_from_all,
)
def m5817a4(c: Cast) -> None:
    """The grab and the combat advantage it carries play, and the disease is
    written.

    **The card prints two ways back and they are different kinds of
    thing.** The die stays in the header, which is what the page shows;
    "if it starts its next turn hidden from all enemies" is the *absence*
    of being seen and no event announces it, so it is a `recharge_while=`
    predicate re-asked at the start of this creature's turn beside the die.
    `m5817a5` prints that sentence, which is why the condition is written
    there and the field is here: the recharge belongs to the row being
    recharged.

    The second half of that sentence is paid here too. `m5817a5` arms
    `_M5817_PAIRED` when the condition held, and this row spends it on a
    free `m5817a3` -- `c.use_power` never charges an action, which is
    exactly "with a single standard action", the standard being this one.

    The card contracts it *at the end of the encounter*, which this engine
    cannot tell from the end of the fight -- so it lands on the hit, one
    round early and the closest this horizon allows. `c.contract` records it;
    the stage does not advance, which is what the page prints."""
    paired = c.first and _m5817_paired(c.world, c.me)
    if c.strike():
        c.hit()
        c.grab(dc=22)
        c.gains_advantage(
            lambda ctx: ctx.get("target") in c.grabbing(of=c.me), until=When.ENCOUNTER,
        )
        c.contract("x5_62")
    # After the swing this row is about, and asked before it: the hold is
    # read at the top because a `When.EONT` effect is still standing either
    # way, and the free attack is the *second* of the two the card pairs.
    if paired:
        c.use_power("m5817a3")


@power(
    "m5817a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_m5817_in_head_form,
    requires_text="the m5817 must be in head form",
)
def m5817a5(c: Cast) -> None:
    """Phases away, and buys itself a paired attack next turn if it is
    still unseen.

    **`c.recast` was the wrong verb, not a missing one.** It repeats a row
    on a clock, and the card's condition is a *state* true at the top of a
    turn -- which is `recharge_while=`, a header field on the row being
    recharged, re-asked by `actions.recharge` beside the die. So the
    recharge half lives on `m5817a4` and `_m5817_hidden_from_all` is the
    predicate both halves share.

    "On that turn it can use that power and bite with a single standard
    action" is the other half, and it needs the moment rather than the
    state: the watch below fires once, at the start of this creature's next
    turn, and arms a hold `m5817a4` spends on a free `m5817a3`. Armed here
    because the clause is this row's sentence; read there because that is
    the standard action being paid with.

    One shot, latched in the closure: a creature acts many times in a
    fight and the condition is about *its next* turn, not about every turn
    after this one."""
    me = c.me
    c.phasing(until=When.SONT)
    c.shift(c.speed_of())
    seen: list[int] = []

    def at_my_next_turn(ev: TurnStart) -> None:
        if seen or ev.actor != me:
            return
        seen.append(1)
        if _m5817_hidden_from_all(c.world, me):
            c.effect(_M5817_PAIRED, on=me, until=When.EONT)

    c.watch(TurnStart, at_my_next_turn, until=When.ENCOUNTER, on=me)


# ==========================================================================
# m5910
# ==========================================================================


@power(
    "m5910a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m5910a0(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    if victim is not None and unseen_by(c.world, victim, c.me):
        c.damage("4d10", 14, on=victim)
    else:
        c.hit()


@power(
    "m5910a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5910a1(c: Cast) -> None:
    _twice(c, "m5910a0")


@power(
    "m5910a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=13),
)
def m5910a2(c: Cast) -> None:
    me = c.me
    if c.first:
        ring = c.zone(c.area(), until=When.EONT, sustain=MINOR, label=c.ref)

        def blind(ev: ZoneEntered) -> None:
            if ev.zone == ring:
                c.blinded(on=ev.actor, until=When.EONT)

        def cure(ev: ZoneExited) -> None:
            if ev.zone == ring and ev.actor != me:
                c.cure(Condition.BLINDED, on=ev.actor)

        c.watch(ZoneEntered, blind, until=When.EONT, on=me, label=f"{c.ref} in")
        c.watch(ZoneExited, cure, until=When.EONT, on=me, label=f"{c.ref} out")
    if c.strike():
        c.blinded(until=When.EONT)


@power(
    "m5910a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5910a3(c: Cast) -> None:
    me = c.me
    held = c.invisible(on=me, until=When.EONT)
    if held is None:
        return

    def seen(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(held, "she attacked")

    c.watch(AttackRolled, seen, until=When.EONT, on=me, once=True, label=f"{c.ref} veil")


@power(
    "m5910a4",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5910a4(c: Cast) -> None:
    c.teleport(5)


_M5910_ATTACKED = "an enemy makes an attack against m5910"


@power(
    "m5910a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5910_ATTACKED,
    on=Trigger(AttackDeclared, targets_me, _M5910_ATTACKED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5910a5(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.teleport(5)


# ==========================================================================
# m6367
# ==========================================================================

_M6367_AURA_OFF = "m6367 aura off"


@power(
    "m6367a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6367a0(c: Cast) -> None:
    me = c.me

    def active(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        if any(eff.label == _M6367_AURA_OFF for eff in c.world.effects.of(me)):
            return False
        return attacker is not None and c.distance(attacker) > 1

    c.conceal(on=me, until=When.ENCOUNTER, when=active)

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.effect(_M6367_AURA_OFF, on=me, until=When.SONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} glare")


@power(
    "m6367a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d4", 9),
)
def m6367a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6367a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("4d6", 4, dtype=DamageType.LIGHTNING),
)
def m6367a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6367a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=Target(side="enemy", everyone=True, label="enemies in the blast"),
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6367a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


_M6367_SHOCKED = "the m6367 hits with m6367a2"


def _hit_with_m6367a2(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and getattr(ev, "power", "") == "m6367a2"


@power(
    "m6367a4",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6367_SHOCKED,
    on=Trigger(Hit, _hit_with_m6367a2, _M6367_SHOCKED),
)
def m6367a4(c: Cast) -> None:
    """The ground turning to black sand is scenery dressing with no stated
    game effect; the burn is the whole mechanical clause."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.ongoing(10, DamageType.NECROTIC, on=victim)


_M6367_HIT = "the m6367 is hit by an attack"


@power(
    "m6367a5",
    level=10,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
    trigger=_M6367_HIT,
    on=Trigger(Hit, targets_me, _M6367_HIT),
    dropped=("c.summon_inline(decoy=)",),
)
def m6367a5(c: Cast) -> None:
    """The teleport and the invisibility play; leaving a double behind that
    carries the m6367's own aura and vanishes if struck has no shorthand --
    `c.summon_inline` defines a whole creature's stats, not a decoy with one
    borrowed trait."""
    me = c.me
    held = c.invisible(on=me, until=When.EONT)
    c.teleport(5)
    if held is None:
        return

    def ends(ev: Hit | Miss) -> None:
        if ev.attacker == me:
            c.world.effects.end(held, "it attacked")

    c.watch(Hit, ends, until=When.EONT, on=me, once=True, label=f"{c.ref} veil")
    c.watch(Miss, ends, until=When.EONT, on=me, once=True, label=f"{c.ref} veil")


# ==========================================================================
# m6373
# ==========================================================================


@power(
    "m6373a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6373a0(c: Cast) -> None:
    me = c.me
    _aura(
        c, 1, lambda who: who in c.enemies(),
        lambda who: c.conceal(on=who, until=When.ENCOUNTER),
    )

    def burn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, burn, until=When.ENCOUNTER, on=me, label=f"{c.ref} grit")


@power(
    "m6373a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.damage_disadvantage(against=)",),
)
def m6373a1(c: Cast) -> None:
    """Forcing an *attacker's* area or close roll to two-and-take-lower is
    the same unsayable shape as `m3295a5` -- nothing hands disadvantage to
    somebody else's roll from the target's side."""


@power(
    "m6373a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6373a2(c: Cast) -> None:
    """Walking on sand and water as solid ground has nothing to stand on
    here -- the audit board carries no such terrain -- so only the
    difficult-terrain half has anything to arm."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m6373a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("", 5, kind=MINION),
)
def m6373a3(c: Cast) -> None:
    if c.strike():
        c.hit()
