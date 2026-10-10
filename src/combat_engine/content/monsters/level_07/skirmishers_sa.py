"""Monster abilities, level 7, skirmishers, second sweep.

161 rows across the thirty-four stat blocks `skirmishers.py`'s first sweep
did not reach. Thirteen of the forty-seven blocks in this slot print no
abilities at all and have nothing to decorate: m2857, m2932, m2961, m2973,
m3000, m3010, m3083, m387, m401, m4780, m4882, m5009, m810.

Conventions, inherited from the six levels below and from this level's own
`skirmishers.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=12)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action word the compendium's own column claims;
* a card that prints no range at all is melee 1; a printed band like
  "6/12" takes the **normal** (shorter) number;
* `half_on_miss=True` is header data only -- a Miss line is also written
  as `else: c.hit(half=True)`;
* a printed Requirement naming a weapon is not asked -- a monster carries
  no `Gear`, and the blow is the block's own basic attack;
* "(crit NdX+n)" that only ever matches the engine's own max-dice-plus-bonus
  needs nothing extra -- it is the same arithmetic `c.hit()` already does.
  Where the crit line names *different* dice or a *different* bonus from the
  plain hit, it is paid by hand with `c.flat(c.roll(dice) + bonus, dtype=...)`
  so a typed hit stays typed on a crit too.

Two generic weapon words a card prints -- "sickle", "rapier", "crossbow",
"maul", "javelin", "glaive" -- are not treated as leaked names: they are the
weapon group, the same kind of word "longsword" already is throughout this
tree, not a creature's or a power's own flavour.

A handful of rows found an engine gap worth naming rather than working
around; each carries a `dropped=` and is explained where it sits. See the
report for the command that confirmed each symbol absent.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_03.brutes import _taking_ongoing as _burning_with
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _is_bloodied,
    _recharge_on,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _adjacent_foes,
    _armed,
    _carries,
    _mobile_attack,
    _nearest,
    _shift_up_to,
)
from combat_engine.content.monsters.level_04.skirmishers import _struck
from combat_engine.content.monsters.level_06.skirmishers import _mobbed
from combat_engine.content.monsters.level_07.brutes import _aura
from combat_engine.content.monsters.level_07.skirmishers import _flying, _taking_ongoing
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
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
    Keyword,
    Melee,
    Mod,
    Movement,
    Ranged,
    Relation,
    Stats,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Dropped,
    Escaped,
    Hit,
    Miss,
    MoveStart,
    RelationSet,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    allies,
    creatures,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    by_opportunity,
    targets_me,
)
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _slowed_or_immobilized_by_me(c: Cast, who: int | None) -> bool:
    """Is that creature slowed or immobilized, and specifically by this one?

    Read off the effect's own `source` rather than just the condition, since
    the printed line names *whose* hold it has to be.
    """
    if who is None:
        return False
    held = (Condition.SLOWED, Condition.IMMOBILIZED)
    return any(
        e.source == c.me and (held[0] in e.conditions or held[1] in e.conditions)
        for e in c.world.effects.of(who)
    )


def _has_adjacent_ally(world: World, eid: int) -> bool:
    return any(distance_between(world, eid, a) <= 1 for a in allies(world, eid))


def _enemy_near_attacks_ally(world: World, me: int, ev: AttackDeclared) -> bool:
    return (
        ev.attacker in enemies(world, me)
        and distance_between(world, me, ev.attacker) <= 5
        and ev.target in allies(world, me)
    )


def _guards_the_target(world: World, me: int, ev: AttackDeclared) -> bool:
    return world.relations.holds(Relation.GUARDED_BY, me, ev.target)


def _granting_ca(ctx: dict[str, Any]) -> bool:
    """"Against any target granting it combat advantage" -- shared by every
    row in this file printing that exact clause, melee-only or not."""
    return bool(ctx.get("advantage"))


def _granting_ca_melee(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("advantage")) and not ctx.get("ranged")


def _no_duplicate_family_member(c: Cast) -> set[int]:
    """The original and every one of its own duplicates, as one set."""
    boss = c.master()
    if boss is None:
        boss = c.me
    return {boss, *c.world.relations.targets(Relation.MASTER_OF, boss)}


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m1094
# --------------------------------------------------------------------------


@power(
    "m1094a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m1094a0(c: Cast) -> None:
    """Doubled dice against a prone target, dealt by hand so a crit's own
    doubling does not double this double."""
    if c.strike():
        c.damage("2d8", 5) if c.is_(Condition.PRONE) else c.hit()


@power("m1094a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1094a1(c: Cast) -> None:
    """A trait, whatever action word the compendium files it under: combat
    advantage against anyone mobbed by the mount's own allies, and a prone
    rider on a hit landed while that advantage is standing."""
    c.gains_advantage(lambda ctx: _mobbed(c, ctx.get("target"), 1), until=When.ENCOUNTER)

    def drop(ev: Hit) -> None:
        if ev.attacker == c.me and ev.result is not None and ev.result.advantage:
            c.prone(on=ev.target)

    c.watch(Hit, drop, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("m1094a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1094a2(c: Cast) -> None:
    """Armed off `RelationSet`, not `requires=`: a rider only exists once
    somebody mounts, and a Requirement on the trait itself would be judged
    before the saddle is ever filled and refused for good. `c.rider`, not
    `relations.sources` -- the direction that reads empty forever."""
    mount = c.me

    def arm(rider: int) -> None:
        stats = c.world.get(rider, Stats)
        if stats is None or stats.level < 5:
            return
        def gate(ctx: dict[str, Any], r: int = rider) -> bool:
            target = ctx.get("target")
            return target is not None and any(
                a != r and distance_between(c.world, a, target) <= 1 for a in c.allies()
            )

        c.gains_advantage(gate, on=rider, until=When.ENCOUNTER)

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == mount:
            arm(ev.target)

    current = c.rider()
    if current is not None:
        arm(current)
    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=mount, label=c.ref)


# --------------------------------------------------------------------------
# m115703
# --------------------------------------------------------------------------


@power(
    "m115703a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m115703a0(c: Cast) -> None:
    others = [f for f in c.enemies() if f != c.target and c.distance(f) <= 1]
    if c.strike():
        c.damage("3d8", 8) if not others else c.hit()


@power(
    "m115703a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.shift(pulls=)",),
)
def m115703a1(c: Cast) -> None:
    """Effect line uses its own claw and reads the hit off the bus. Hauling
    the target along with the shift has no verb -- `shift`'s own `share=`
    only lets a mover land on an occupied square, not drag a second
    creature with it, the same gap `level_05/brutes.py`'s `m217a3` already
    found and named. The miss half plays in full."""
    hit = _struck(c, "m115703a0", 1)
    c.shift(4 if hit else c.speed_of())


def _near_tree(world: World, eid: int) -> bool:
    from combat_engine.engine.query import scenery

    return bool(scenery(world, "tree", within=1, of=eid))


@power(
    "m115703a2",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_near_tree,
    requires_text="it must be adjacent to a tree or a Large plant",
)
def m115703a2(c: Cast) -> None:
    """Checked against standing scenery tagged "tree"; a Large plant
    creature is the rarer half of the printed either/or and is not asked."""
    c.teleport(8)


@power(
    "m115703a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m115703a3(c: Cast) -> None:
    """A disguise with nothing for a fight to read -- appearance has no
    combat shape here."""


# --------------------------------------------------------------------------
# m115779
# --------------------------------------------------------------------------


@power(
    "m115779a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m115779a0(c: Cast) -> None:
    """Checked before the swing, since making this attack is itself what
    ends the shadow form (a2) -- by the time the roll has happened, the
    form the card asks about is already gone."""
    shadowed = _armed(c, "m115779a2")
    if c.strike():
        c.damage("4d6", 8) if shadowed else c.hit()


def _anybody_adjacent(world: World, eid: int) -> bool:
    return any(
        other != eid and distance_between(world, eid, other) <= 1 for other in creatures(world)
    )


@power(
    "m115779a1",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_anybody_adjacent,
    requires_text="it must be adjacent to a creature",
)
def m115779a1(c: Cast) -> None:
    c.teleport(3)
    c.cure(Condition.MARKED, on=c.me)


@power(
    "m115779a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m115779a2(c: Cast) -> None:
    """Recharges on a printed sentence rather than only a die. The form ends
    on the creature's own next attack roll -- watched here rather than left
    to a0, so it ends the instant the roll happens and not only when a0
    itself is the attack -- or lapses on its own if never sustained.
    `c.insubstantial`/`c.vulnerable` carry no sustain cost of their own, so
    `until=When.SUSTAIN` on them directly would drop both after one round
    regardless of sustaining; they ride the anchor's `on_end` instead."""
    _recharge_when_bloodied(c)
    anchor = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    if anchor is None:
        return
    insub = c.insubstantial(on=c.me, until=When.ENCOUNTER)
    vuln = c.vulnerable(5, DamageType.RADIANT, on=c.me, until=When.ENCOUNTER)
    for eff in (insub, vuln):
        if eff is not None:
            anchor.on_end.append(lambda e=eff: c.world.effects.end(e, "the form ended"))

    def ended_by_attack(ev: AttackRolled) -> None:
        if ev.attacker == c.me:
            c.world.effects.end(anchor, "it made an attack roll")

    c.watch(
        AttackRolled, ended_by_attack,
        until=When.ENCOUNTER, on=c.me, once=True, label=f"{c.ref} ends",
    )


# --------------------------------------------------------------------------
# m115846
# --------------------------------------------------------------------------


@power(
    "m115846a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m115846a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115846a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 9),
)
def m115846a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115846a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115846a2(c: Cast) -> None:
    """Effect line fires its own javelin and reads the hit off the bus."""
    hit = _struck(c, "m115846a1", 1)
    if hit:
        c.charge_at(hit[0])


@power(
    "m115846a3",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=10),
)
def m115846a3(c: Cast) -> None:
    """"If the attack hits any of the targets" is an aggregate across the
    whole burst, tracked in a plain dict keyed by caster rather than
    guessed from one target's own result."""
    if c.first:
        _HIT_TALLY[c.me] = False
    if c.strike():
        c.push(2)
        _HIT_TALLY[c.me] = True
    if c.last and _HIT_TALLY.pop(c.me, False):
        c.move(c.speed_of())


_HIT_TALLY: dict[int, bool] = {}


# --------------------------------------------------------------------------
# m1166
# --------------------------------------------------------------------------


@power(
    "m1166a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m1166a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d8"))


@power(
    "m1166a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m1166a1(c: Cast) -> None:
    """No range prints for this one either -- melee 1 by the same
    convention as a0, the crossbow half of a3's either/or."""
    if c.strike():
        c.hit()


@power(
    "m1166a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m1166a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power("m1166a3", level=7, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m1166a3(c: Cast) -> None:
    """"Makes two longsword or two crossbow attacks" -- a choice the policy
    makes once, then two swings of the chosen weapon."""
    ref = c.choose(["m1166a0", "m1166a1"], f"{c.ref}: which weapon") or "m1166a0"
    for _ in range(2):
        use(c.world, c.me, ref, spend=False)


@power("m1166a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1166a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


@power("m1166a5", level=7, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m1166a5(c: Cast) -> None:
    c.shift(2)


@power(
    "m1166a6",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=10),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m1166a6(c: Cast) -> None:
    c.shift(1)
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    if c.strike(on=attacker):
        c.cure(Condition.MARKED, on=c.me)
        c.grants_advantage(on=attacker, until=When.EONT)


@power(
    "m1166a7",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m1166a7(c: Cast) -> None:
    """Three poisons, chosen without being named -- see the report. Applying
    a second replaces the watch, which is what wastes whichever one was
    still waiting."""
    choice = c.choose(["1", "2", "3"], f"{c.ref}: which poison")
    if choice is None:
        return
    for old in list(c.world.effects.of(c.me)):
        if old.label == c.ref:
            c.world.effects.end(old, "a new poison replaced it")

    def secondary(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if choice == "1":
            if c.attack(10, WILL, on=ev.target):
                c.blinded(on=ev.target, until=When.SAVE_ENDS)
        elif choice == "2":
            if c.attack(10, FORT, on=ev.target):
                c.immobilized(on=ev.target, until=When.SAVE_ENDS)
        else:
            if c.attack(10, FORT, on=ev.target):
                c.ongoing(5, on=ev.target)
                c.slowed(on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, secondary, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power("m1166a8", level=7, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m1166a8(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, once=True, until=When.ENCOUNTER,
        when=_granting_ca,
    )


# --------------------------------------------------------------------------
# m1742
# --------------------------------------------------------------------------


@power(
    "m1742a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m1742a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1742a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
    requires=lambda world, eid: bool(world.relations.targets(Relation.MASTER_OF, eid)),
    requires_text="it must have a duplicate",
)
def m1742a1(c: Cast) -> None:
    """Needs a duplicate to exist at all -- the Requirement -- but which
    square the burst actually lands on is the board's own pick rather than
    forced onto a duplicate's square; `within=10` is the leash a2 already
    puts on a duplicate, so it is a real distance and not an invented one.
    Miss deals no damage at all, so the Miss branch is written bare."""
    if c.first:
        c.flat(15, on=c.me)
    if c.strike():
        c.hit()
    c.dazed(until=When.SAVE_ENDS)


@power(
    "m1742a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.PSYCHIC],
    requires=lambda world, eid: not _is_bloodied(world, eid),
    requires_text="not usable while bloodied",
    dropped=("c.unsummon()",),
)
def m1742a2(c: Cast) -> None:
    """Up to four at once, tracked through `MASTER_OF` so `c.servants()`
    answers the cap and lets the rest of this block find them. Ending one
    early -- it strays past 10 squares, or the m1742 itself drops -- has no
    verb; see the report."""
    if len(c.servants()) >= 4:
        return
    sq = _free_square_beside(c, c.me)
    if sq is None:
        return
    health = c.world.get(c.me, Health)
    if health is None:
        return
    share = max(1, health.hp // 4)
    c.flat(share, on=c.me)
    dup = c.summon("m1742", at=sq)
    if dup == 0:
        return
    dup_health = c.world.get(dup, Health)
    if dup_health is not None:
        dup_health.hp = share
    c.bind(on=dup)
    c.deals(DamageType.PSYCHIC, on=dup, until=When.ENCOUNTER)


@power(
    "m1742a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=lambda world, eid: any(
        distance_between(world, eid, s) <= 1
        for s in world.relations.targets(Relation.MASTER_OF, eid)
    ),
    requires_text="it must have a duplicate adjacent to it",
    dropped=("c.unsummon()",),
)
def m1742a3(c: Cast) -> None:
    """Clears the bond and takes the heal; actually removing the absorbed
    duplicate from the board has no verb -- see a2 and the report."""
    dup = next((s for s in c.servants() if c.distance(s) <= 1), None)
    if dup is None:
        return
    c.world.relations.clear(Relation.MASTER_OF, c.me, dup, c.ref)
    c.heal(30, on=c.me)


@power("m1742a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1742a4(c: Cast) -> None:
    """"Flanks an enemy with another duplicate" narrows ordinary flanking to
    a flanking partner from this creature's own duplicate family -- read as
    genuine flanking plus a family member adjacent, rather than reworking
    the grid geometry for one trait."""

    def when(ctx: dict[str, Any]) -> bool:
        target = ctx.get("target")
        if target is None or ctx.get("ranged") or not flanked_by(c.world, target, c.me):
            return False
        family = _no_duplicate_family_member(c) - {c.me}
        return any(distance_between(c.world, m, target) <= 1 for m in family)

    c.bonus("damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=when)


@power(
    "m1742a5",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it is damaged by an attack",
    on=Trigger(Hit, targets_me, "it is damaged by an attack"),
    dropped=("c.redirect(dtype=)",),
)
def m1742a5(c: Cast) -> None:
    """`c.redirect` moves the blow; it has no way to recolour it, so the
    duplicate takes whatever type actually rolled rather than psychic --
    see the report."""
    dup = c.choose(c.servants(), f"{c.ref}: which duplicate", optional=True)
    if dup is not None:
        c.redirect(to=dup)


# --------------------------------------------------------------------------
# m1799
# --------------------------------------------------------------------------


@power(
    "m1799a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 7),
)
def m1799a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1799a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 9, kind=LIMITED),
)
def m1799a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


def _adjacent_enemy_moving(world: World, me: int, ev: MoveStart) -> bool:
    return ev.actor in enemies(world, me) and distance_between(world, me, ev.actor) <= 1


@power(
    "m1799a2",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d4", 3),
    trigger="an adjacent enemy moves away",
    on=Trigger(MoveStart, _adjacent_enemy_moving, "an adjacent enemy moves away"),
)
def m1799a2(c: Cast) -> None:
    """`MoveStart`, not `MoveEnd`: by the time the enemy has actually left,
    `c.adjacent` is false precisely when the row should fire."""
    foe = c.trigger.actor  # type: ignore[union-attr]
    if c.strike(on=foe):
        c.hit(on=foe)
        c.shift(1)
        dest = _free_square_beside(c, c.me)
        c.slide(1, on=foe, to=dest) if dest is not None else c.slide(1, on=foe)


@power("m1799a3", level=7, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m1799a3(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m1803
# --------------------------------------------------------------------------


@power(
    "m1803a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m1803a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1803a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("4d6", 5, kind=LIMITED),
)
def m1803a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.dazed(until=When.SAVE_ENDS)


@power("m1803a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1803a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=_granting_ca_melee,
    )


# --------------------------------------------------------------------------
# m1805
# --------------------------------------------------------------------------


@power(
    "m1805a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 9),
)
def m1805a0(c: Cast) -> None:
    """+2 more while bloodied, and the crit line follows for free: the
    engine's own max-dice-on-crit already lands on the printed numbers
    once the bonus itself is right."""
    bonus = 2 if c.bloodied(on=c.me) else 0
    if c.strike():
        c.damage("1d6", 9 + bonus)


@power(
    "m1805a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 9),
)
def m1805a1(c: Cast) -> None:
    bonus = 2 if c.bloodied(on=c.me) else 0
    if c.strike():
        c.damage("1d6", 9 + bonus)


@power(
    "m1805a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 9),
)
def m1805a2(c: Cast) -> None:
    bonus = 2 if c.bloodied(on=c.me) else 0
    c.shift(2)
    if c.strike():
        c.damage("1d6", 9 + bonus)
    c.shift(2)


@power("m1805a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1805a3(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _mobbed(c, ctx.get("target"), 2),
    )


# --------------------------------------------------------------------------
# m2097
# --------------------------------------------------------------------------


@power(
    "m2097a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 2, dtype=DamageType.POISON),
)
def m2097a0(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.flat(c.roll("1d8") + 18, dtype=DamageType.POISON)
        else:
            c.hit()


@power(
    "m2097a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5, dtype=DamageType.POISON),
)
def m2097a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2097a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m2097a2(c: Cast) -> None:
    _mobile_attack(c, 3)


@power(
    "m2097a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d8", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2097a3(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.flat(c.roll("1d8") + 29, dtype=DamageType.POISON)
        else:
            c.hit()
        victim = c.target
        if victim is not None:
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.flat(6, dtype=DamageType.POISON, on=foe)


@power(
    "m2097a4",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    dropped=("c.invisible(reveal=)",),
)
def m2097a4(c: Cast) -> None:
    """The concealment half is `c.no_cover`, which says exactly "does not
    benefit from cover or concealment." Seeing through the target's own
    invisibility for every attacker, not just this one, has no verb --
    see the report."""
    if c.strike():
        c.grants_advantage(to="team", until=When.EONT)
        c.no_cover(on=c.target, until=When.EONT)


# --------------------------------------------------------------------------
# m2785
# --------------------------------------------------------------------------


@power(
    "m2785a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m2785a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2785a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m2785a1(c: Cast) -> None:
    c.basic()
    c.heal(19, on=c.me)


@power("m2785a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2785a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


@power(
    "m2785a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2785a3(c: Cast) -> None:
    for ally in c.allies():
        kinds = c.kinds_of(on=ally)
        if c.distance(ally) <= 5 and "natural" in kinds and "beast" in kinds:
            c.grant_action("shift", FREE, on=ally)


@power(
    "m2785a4",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m2785a4(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    mate = next(
        (
            a
            for a in c.allies()
            if "natural" in c.kinds_of(on=a)
            and "beast" in c.kinds_of(on=a)
            and distance_between(c.world, a, attacker) <= 1
        ),
        None,
    )
    if mate is not None:
        c.basic(on=attacker, who=mate)
    c.shift(1)


# --------------------------------------------------------------------------
# m3231
# --------------------------------------------------------------------------


@power(
    "m3231a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m3231a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m3231a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3231a1(c: Cast) -> None:
    """Expressed as the one extra point on top of the engine's own automatic
    charge bonus -- "+2 instead of +1" is the same number either way. The
    shift afterward rides a watch on the charge's own Hit/Miss, which is the
    part a passive bonus cannot pay by itself."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")) and _flying(c.world, c.me),
    )

    def after(ev: Any) -> None:
        if ev.attacker == c.me and getattr(ev, "charge", False):
            c.shift(2)

    c.watch(Hit, after, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} land")
    c.watch(Miss, after, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} land miss")


@power("m3231a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3231a2(c: Cast) -> None:
    """Armed off `RelationSet`, the same shape as m1094a2: a rider only
    exists once somebody mounts."""
    mount = c.me

    def arm(rider: int) -> None:
        stats = c.world.get(rider, Stats)
        if stats is None or stats.level < 7:
            return
        for d in ALL_DEFENCES:
            c.bonus(
                d, 1, on=rider, kind="untyped", until=When.ENCOUNTER,
                when=lambda ctx: _flying(c.world, mount),
            )

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == mount:
            arm(ev.target)

    current = c.rider()
    if current is not None:
        arm(current)
    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=mount, label=c.ref)


@power("m3231a3", level=7, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET)
def m3231a3(c: Cast) -> None:
    c.hover(until=When.EONT)


# --------------------------------------------------------------------------
# m3234
# --------------------------------------------------------------------------


@power("m3234a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3234a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


@power(
    "m3234a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3234a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.marked(by=c.target):
            c.cure(Condition.MARKED, on=c.me)


@power(
    "m3234a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m3234a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3234a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m3234a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
        c.dazed(until=When.EONT)


@power(
    "m3234a4",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
)
def m3234a4(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m3234a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m3234a5(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(1)


# --------------------------------------------------------------------------
# m3257
# --------------------------------------------------------------------------


@power(
    "m3257a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 7),
)
def m3257a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3257a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3257a1(c: Cast) -> None:
    """No attack line of its own -- two swings of its basic sickle (a0)
    against one target, redirected to whoever it has combat advantage
    against rather than refused when the chooser aims it elsewhere."""

    _recharge_on(c, Bloodied, lambda ev: ev.actor in c.enemies())
    victim = _restricted_to(c, 1, lambda foe: has_combat_advantage(c.world, c.me, foe))
    if victim is None:
        return
    hits = _struck(c, "m3257a0", 2, victim)
    if len(hits) >= 2:
        c.ongoing(5, on=victim)
        c.dazed(on=victim, until=When.EONT)


@power(
    "m3257a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
)
def m3257a2(c: Cast) -> None:

    _recharge_on(c, Bloodied, lambda ev: ev.actor in c.enemies())
    if c.strike():
        c.push(1)
    c.shift(3)


def _hit_while_bloodied(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and _is_bloodied(world, me)


@power(
    "m3257a3",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack while bloodied",
    on=Trigger(Hit, _hit_while_bloodied, "it is hit by an attack while bloodied"),
)
def m3257a3(c: Cast) -> None:
    c.shift(1)


@power("m3257a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3257a4(c: Cast) -> None:
    from combat_engine.engine import get

    def rider(ev: Hit) -> None:
        if ev.attacker != c.me or not (ev.result is not None and ev.result.advantage):
            return
        row = get(ev.power or "")
        if row is None or row.reach.kind != "melee":
            return
        if _taking_ongoing(c, ev.target):
            return
        c.ongoing(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("m3257a5", level=7, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m3257a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, once=True, until=When.EONT,
        when=_granting_ca,
    )


# --------------------------------------------------------------------------
# m3459
# --------------------------------------------------------------------------


@power(
    "m3459a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3459a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3459a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m3459a1(c: Cast) -> None:
    """Recharges after its own basic attack (a0) lands -- the printed line
    names a power by a word this file does not repeat, and a0 is the only
    weapon swing the block has."""
    _recharge_on(c, Hit, lambda ev: ev.attacker == c.me and ev.power == "m3459a0")
    victim = c.target
    if c.strike() and victim is not None:
        c.gains_advantage(lambda ctx, v=victim: ctx.get("target") == v, until=When.ENCOUNTER)


@power(
    "m3459a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 4),
)
def m3459a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power("m3459a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3459a3(c: Cast) -> None:
    def rider(ev: Hit) -> None:
        from combat_engine.engine import get

        row = get(ev.power or "") if ev.attacker == c.me else None
        if row is not None and row.reach.kind == "melee":
            c.temp_hp(3, on=c.me)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("m3459a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3459a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


# --------------------------------------------------------------------------
# m3464
# --------------------------------------------------------------------------


@power(
    "m3464a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m3464a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3464a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 3),
)
def m3464a1(c: Cast) -> None:
    """"Before or after" -- before, picked once rather than offered twice."""
    c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m3464a2",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy attacks a creature it is guarding",
    on=Trigger(AttackDeclared, _guards_the_target, "an enemy attacks a creature it is guarding"),
)
def m3464a2(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    _shift_up_to(c, 2, toward=attacker)
    if c.adjacent(attacker):
        _struck(c, "m3464a0", 1, attacker)


@power(
    "m3464a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3464a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


# --------------------------------------------------------------------------
# m3467
# --------------------------------------------------------------------------


@power(
    "m3467a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m3467a0(c: Cast) -> None:
    c.shift(2)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3467a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3467a1(c: Cast) -> None:
    """Two rakes during a 7-square shift -- the same shape `_mobile_attack`
    uses, doubled by hand."""
    struck: set[int] = set()
    remaining = 7
    for _ in range(2):
        step = max(1, remaining // 2) if remaining else 0
        if step:
            c.shift(step)
            remaining -= step
        foe = next((f for f in _adjacent_foes(c) if f not in struck), None)
        if foe is not None:
            struck.add(foe)
            _struck(c, "m3467a0", 1, foe)
    if remaining > 0:
        c.shift(remaining)


@power(
    "m3467a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3467a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d8", dtype=DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=_granting_ca,
    )


@power("m3467a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3467a3(c: Cast) -> None:
    c.gains_advantage(
        lambda ctx: _burning_with(c, ctx.get("target"), DamageType.NECROTIC), until=When.ENCOUNTER
    )


# --------------------------------------------------------------------------
# m4242
# --------------------------------------------------------------------------


@power(
    "m4242a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 3),
)
def m4242a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4242a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 3),
)
def m4242a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4242a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
    requires=_has_adjacent_ally,
    requires_text="it must be adjacent to one or more allies",
)
def m4242a2(c: Cast) -> None:
    """"Aftereffect: slowed (save ends)" fires on a **successful** save
    against the restrain, which `escalate=` cannot say -- that hook only
    answers a failure. Watched off `ConditionEnded`'s own `why` instead."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hold = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    if hold is None or victim is None:
        return

    def after(ev: ConditionEnded) -> None:
        if ev.target == victim and ev.condition is Condition.RESTRAINED and ev.why == "saved":
            c.slowed(on=victim, until=When.SAVE_ENDS)

    c.watch(ConditionEnded, after, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power(
    "m4242a3",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "it hits with a melee attack"),
)
def m4242a3(c: Cast) -> None:
    victim = c.trigger.target  # type: ignore[union-attr]
    c.grants_advantage(on=victim, until=When.EONT)
    c.shift(1)


@power("m4242a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4242a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=_granting_ca_melee,
    )


@power(
    "m4242a5",
    level=7,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m4242a5(c: Cast) -> None:
    c.reroll_attack()


# --------------------------------------------------------------------------
# m4364
# --------------------------------------------------------------------------


@power(
    "m4364a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m4364a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power("m4364a1", level=7, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m4364a1(c: Cast) -> None:
    """Two short sword swings -- rolled here rather than through a0, which
    carries its own shift and would double it."""
    for _ in range(2):
        c.shift(1)
        if c.attack(12, AC):
            c.damage("2d6", 4)
    c.shift(1)


@power(
    "m4364a2",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    dropped=("c.invisible(reveal=)",),
)
def m4364a2(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(to="team", until=When.EONT)
        c.no_cover(on=c.target, until=When.EONT)


@power(
    "m4364a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m4364a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.last:
        c.shift(3)


@power(
    "m4364a4",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses it with a melee attack"),
)
def m4364a4(c: Cast) -> None:
    c.shift(1)
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    c.grants_advantage(on=attacker, until=When.EONT)


@power("m4364a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4364a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


# --------------------------------------------------------------------------
# m4450
# --------------------------------------------------------------------------


@power(
    "m4450a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 5),
)
def m4450a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4450a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 5),
)
def m4450a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4450a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 5, kind=LIMITED),
)
def m4450a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4450a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4450a3(c: Cast) -> None:
    def crowded(ev: TurnStart) -> bool:
        near = sum(1 for f in c.enemies() if c.distance(f) <= 1)
        return ev.actor == c.me and not ev.ghost and near > 1

    _recharge_on(c, TurnStart, crowded)
    c.cure(Condition.MARKED, on=c.me)
    c.shift(3)


@power("m4450a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4450a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )


@power("m4450a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4450a5(c: Cast) -> None:
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# --------------------------------------------------------------------------
# m4640
# --------------------------------------------------------------------------


@power(
    "m4640a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m4640a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m4640a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m4640a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4640a2",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 6),
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m4640a2(c: Cast) -> None:
    attacker = getattr(c.trigger, "source", None)
    if attacker is None or attacker not in c.enemies():
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)


@power(
    "m4640a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    no_provoke=True,
)
def m4640a3(c: Cast) -> None:
    """One rapier swing and one crossbow swing against the same target,
    rolled here rather than through a0/a1 -- both carry their own shift
    and would double it."""
    foe = _nearest(c)
    if foe is None:
        return
    c.shift(1)
    if c.attack(12, AC, on=foe):
        c.damage("1d8", 6, on=foe)
    if c.attack(12, AC, on=foe):
        c.damage("2d6", 4, on=foe)
    c.shift(1)


@power(
    "m4640a4",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("4d10", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4640a4(c: Cast) -> None:
    """"If it misses all targets" is an aggregate across the whole burst,
    the same shape m115846a3 tracks."""
    if c.first:
        _MISS_TALLY[c.me] = True
    if c.strike():
        c.hit()
        c.push(1)
        _MISS_TALLY[c.me] = False
    if c.last and _MISS_TALLY.pop(c.me, True):
        c.grants_advantage(until=When.EONT)


_MISS_TALLY: dict[int, bool] = {}


@power(
    "m4640a5",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "it hits with a melee attack"),
)
def m4640a5(c: Cast) -> None:
    c.cure(Condition.DAZED, Condition.IMMOBILIZED, on=c.me)
    c.shift(1)


# --------------------------------------------------------------------------
# m5338
# --------------------------------------------------------------------------


@power(
    "m5338a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5),
)
def m5338a0(c: Cast) -> None:
    ca = c.target is not None and has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.damage("4d6" if ca else "3d6", 5)


@power(
    "m5338a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5338a1(c: Cast) -> None:
    """A rampage along its own shift, approximated: an enemy it ends up
    beside during the move is treated as "entered", rather than tracking the
    exact square-by-square path the printed line describes."""
    speed = c.speed_of()
    entered: set[int] = set()
    for _ in range(speed):
        c.shift(1, share=True)
        for foe in _adjacent_foes(c):
            if foe not in entered:
                entered.add(foe)
                if c.attack(10, REF, on=foe):
                    c.damage("3d10", 5, on=foe)
                    c.prone(on=foe)


@power(
    "m5338a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5, dtype=DamageType.LIGHTNING),
    once_per_round=True,
)
def m5338a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power("m5338a3", level=7, usage=ENCOUNTER, action=MINOR,
       # "Choose one creature that it can see": a sight-based selection, where
       # a personal reach narrows the pool to whoever is adjacent (#427).
       reach=Ranged(20), target=ONE_CREATURE)
def m5338a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.gains_advantage(lambda ctx, v=victim: ctx.get("target") == v, until=When.ENCOUNTER)
    c.truesight(of=victim, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m5571
# --------------------------------------------------------------------------


@power(
    "m5571a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m5571a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5571a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 5),
)
def m5571a1(c: Cast) -> None:
    """Redirected to a qualifying victim rather than refused when the
    chooser aims elsewhere -- `Target` has no field for a condition."""
    down = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)
    victim = _restricted_to(c, 1, lambda foe: any(c.is_(cond, on=foe) for cond in down))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(on=victim, until=When.SAVE_ENDS)


@power(
    "m5571a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5571a2(c: Cast) -> None:
    c.jump(8)


def _grabbed_tries_to_escape(world: World, me: int, ev: Escaped) -> bool:
    return ev.holder == me


@power(
    "m5571a3",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
    trigger="a creature it is grabbing attempts to escape",
    on=Trigger(Escaped, _grabbed_tries_to_escape, "a creature it is grabbing attempts to escape"),
)
def m5571a3(c: Cast) -> None:
    victim = c.trigger.actor  # type: ignore[union-attr]
    if c.strike(on=victim):
        c.hit(on=victim)


# --------------------------------------------------------------------------
# m5644
# --------------------------------------------------------------------------


@power("m5644a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5644a0(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _mobbed(c, ctx.get("target"), 2),
    )


@power(
    "m5644a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m5644a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5644a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m5644a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power("m5644a3", level=7, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m5644a3(c: Cast) -> None:
    c.shift(4)


@power(
    "m5644a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5644a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5674
# --------------------------------------------------------------------------


@power("m5674a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5674a0(c: Cast) -> None:
    acted: set[int] = set()

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} acted")
    c.bonus(
        "damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") not in acted,
    )


@power(
    "m5674a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5674a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5674a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m5674a2(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    part = max(1, half // 2)
    c.shift(part)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
        _struck(c, "m5674a1", 1, foe)
    c.shift(half - part)


@power(
    "m5674a3",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy within 5 squares attacks an ally",
    on=Trigger(
        AttackDeclared, _enemy_near_attacks_ally, "an enemy within 5 squares attacks an ally"
    ),
)
def m5674a3(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    _shift_up_to(c, c.speed_of(), toward=attacker)
    if c.adjacent(attacker):
        _struck(c, "m5674a1", 1, attacker)


# --------------------------------------------------------------------------
# m5730
# --------------------------------------------------------------------------


@power("m5730a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5730a0(c: Cast) -> None:
    """`c.aura` makes no difficult terrain of its own -- only `c.zone` takes
    that flag -- so the zone it creates is flagged by hand afterward, and
    allies are exempted so the "for enemies" half is not lost."""
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)
    zone = c.world.get(ring, Zone)
    if zone is not None:
        zone.difficult = True
    c.ignores_difficult_in(ring, side="team")


@power(
    "m5730a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m5730a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5730a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 1),
)
def m5730a2(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m5730a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5730a3(c: Cast) -> None:
    c.move(5, at="fly")


def _hit_with_m5730a1(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m5730a1"


@power(
    "m5730a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it hits with m5730a1",
    on=Trigger(Hit, _hit_with_m5730a1, "it hits with m5730a1"),
)
def m5730a4(c: Cast) -> None:
    def recharged(ev: DamageApplied) -> bool:
        return ev.target == c.me and DamageType.PSYCHIC in ev.types()

    _recharge_on(c, DamageApplied, recharged)
    victim = c.trigger.target  # type: ignore[union-attr]
    c.flat(c.roll("2d6"), dtype=DamageType.PSYCHIC, on=victim)


# --------------------------------------------------------------------------
# m5738
# --------------------------------------------------------------------------


@power("m5738a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5738a0(c: Cast) -> None:
    """Two halves: standing permission to walk through a slowed or
    immobilized enemy's square, and immunity from that same enemy's own
    opportunity attacks."""
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=False)
    c.no_provoke(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _slowed_or_immobilized_by_me(c, ctx.get("attacker")),
    )


@power(
    "m5738a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4),
)
def m5738a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5738a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d10", 4, dtype=DamageType.POISON),
)
def m5738a2(c: Cast) -> None:
    """Redirected to whoever it has slowed, rather than refused when the
    chooser aims elsewhere."""

    def slowed_by_me(foe: int) -> bool:
        return c.is_(Condition.SLOWED, on=foe) and _slowed_or_immobilized_by_me(c, foe)

    victim = _restricted_to(c, 1, slowed_by_me)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)

        def worsen(eff: Effect) -> None:
            c.world.effects.end(eff, "the poison worsened")
            c.condition(
                Condition.IMMOBILIZED,
                until=When.SAVE_ENDS,
                on=victim,
                ongoing=(5, DamageType.POISON),
            )

        c.condition(
            until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON), escalate=worsen
        )


# --------------------------------------------------------------------------
# m5829
# --------------------------------------------------------------------------


@power("m5829a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5829a0(c: Cast) -> None:
    def hold(who: int) -> Effect | None:
        return c.world.effects.apply(
            who, c.me, When.ENCOUNTER, label=c.ref,
            mods=[(who, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        )

    _aura(c, 1, lambda who: who in c.enemies(), hold)


@power("m5829a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5829a1(c: Cast) -> None:
    """Halving is `DamageRolled` in the `BEFORE` window, where the number
    still exists and can be changed -- the pattern `level_06/controllers.py`
    settled for the same printed shape."""
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target == me and ev.dtype is not DamageType.FORCE:
            ev.amount //= 2

    c.watch(DamageRolled, soften, until=When.ENCOUNTER, on=me, window=Window.BEFORE, label=c.ref)


@power("m5829a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5829a2(c: Cast) -> None:
    def dropped(ev: Dropped) -> None:
        if ev.actor == c.me or ev.actor not in c.allies():
            return
        if c.distance(ev.actor) > 5 or not _carries(c.world, ev.actor, "m5829a1"):
            return
        c.bonus("attack", 2, on=c.me, kind="power", until=When.EONT)

    c.watch(Dropped, dropped, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m5829a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m5829a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5829a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m5829a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5829a5",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m5829a5(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(4)
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5917
# --------------------------------------------------------------------------


@power("m5917a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5917a0(c: Cast) -> None:
    """Applied as a standing fact rather than only while a3's disguise is
    specifically an undead one -- there is no board state yet distinguishing
    which of a3's forms is current, and `is_kind("undead")` is all the
    printed clause is ever read through."""
    c.set_origin("undead", on=c.me, until=When.ENCOUNTER)


@power("m5917a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5917a1(c: Cast) -> None:
    def rider(ev: Hit) -> None:
        advantaged = ev.result is not None and ev.result.advantage
        if ev.attacker != c.me or ev.target is None or not advantaged:
            return
        dice = "2d6"
        if flanked_by(c.world, ev.target, c.me) and any(
            "undead" in c.kinds_of(on=m) and distance_between(c.world, m, ev.target) <= 1
            for m in c.allies()
        ):
            dice = "3d6"
        c.flat(c.roll(dice), on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m5917a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m5917a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5917a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5917a3(c: Cast) -> None:
    """A disguise with nothing for a fight to read -- appearance has no
    combat shape here, same as m3641a5 at level 6."""


@power(
    "m5917a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 5, half_on_miss=True),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5917a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.prone()


@power(
    "m5917a5",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="its movement triggers an attack against it",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_opportunity),
        "its movement triggers an attack against it",
    ),
)
def m5917a5(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    mate = next(
        (
            a
            for a in c.allies()
            if "undead" in c.kinds_of(on=a) and distance_between(c.world, a, attacker) <= 1
        ),
        None,
    )
    if mate is not None:
        c.redirect(to=mate)


# --------------------------------------------------------------------------
# m5925
# --------------------------------------------------------------------------


@power("m5925a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5925a0(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5925a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5925a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5925a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5925a2(c: Cast) -> None:
    """Recharges on a miss, which is the printed condition, not the die."""
    c.shift(c.speed_of())
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is None:
        return
    if c.attack(10, REF, on=foe):
        c.damage("4d6", 4, on=foe)
        c.push(1, on=foe)
        c.dazed(on=foe, until=When.SAVE_ENDS)
    else:
        c.restore_use(c.ref, on=c.me)


@power(
    "m5925a3", level=7, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET
)
def m5925a3(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    c.shift(half)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None and c.attack(10, REF, on=foe):
        c.damage("2d6", 8, on=foe)
    c.shift(c.speed_of() - half)


# --------------------------------------------------------------------------
# m5954
# --------------------------------------------------------------------------


@power(
    "m5954a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5954a0(c: Cast) -> None:
    """"Before or after" -- before, picked once rather than offered twice."""
    c.shift(3)
    if c.strike():
        c.hit()


@power("m5954a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5954a1(c: Cast) -> None:
    """Effect line uses its own a0 twice -- the shift it carries each time
    is part of what "using m5954a0" means, not a second shift laid on top."""
    _struck(c, "m5954a0", 2)
    c.bonus(AC, 2, on=c.me, kind="power", until=When.SONT)


@power(
    "m5954a2",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5954a2(c: Cast) -> None:
    """"Entirely within the zone" is read as being in it at all -- the zone
    system diffs by any overlap of occupied squares, not every one of
    them, which only differs for a creature bigger than the burst."""
    area = spread({c.here}, 1)
    ring = c.zone(area, blocks_sight=True, until=When.EONT, label=c.ref)
    me = c.me
    held: dict[int, Effect] = {}

    def blind(who: int) -> None:
        if who == me or who in held:
            return
        effect = c.condition(Condition.BLINDED, until=When.ENCOUNTER, on=who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            blind(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the zone")

    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        blind(actor)


def _adjacent_enemy_hits_me(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.target == me
        and ev.attacker in enemies(world, me)
        and distance_between(world, me, ev.attacker) <= 1
        and by_melee(world, me, ev)
    )


@power(
    "m5954a3",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an adjacent enemy hits it with a melee attack",
    on=Trigger(Hit, _adjacent_enemy_hits_me, "an adjacent enemy hits it with a melee attack"),
)
def m5954a3(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    hit = _struck(c, "m5954a0", 1, attacker)
    if hit:
        c.grants_advantage(on=attacker, until=When.EONT)
    else:
        c.grants_advantage(on=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m6434
# --------------------------------------------------------------------------


@power("m6434a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6434a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None and flanked_by(c.world, ctx["target"], c.me),
    )


@power(
    "m6434a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 3),
)
def m6434a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# --------------------------------------------------------------------------
# m6609
# --------------------------------------------------------------------------


@power("m6609a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6609a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def toll(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            c.flat(5, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} toll")


@power("m6609a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6609a1(c: Cast) -> None:
    """The engine's own slow formula already leaves a flyer's fly speed
    untouched -- `c.move`'s own compensation hands it back in full -- so the
    printed exception ("only the fly speed") needs the opposite push: the
    fly mode's own number is capped by hand while slowed, and handed back
    when the condition clears."""
    me = c.me
    saved: dict[str, int] = {}

    def slowed_on(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.SLOWED or "fly" in saved:
            return
        moves = c.world.get(me, Movement)
        if moves is not None and "fly" in moves.modes:
            saved["fly"] = moves.modes["fly"]
            moves.modes["fly"] = min(moves.modes["fly"], 2)

    def slowed_off(ev: ConditionEnded) -> None:
        if ev.target != me or ev.condition is not Condition.SLOWED or "fly" not in saved:
            return
        moves = c.world.get(me, Movement)
        if moves is not None:
            moves.modes["fly"] = saved.pop("fly")

    c.watch(ConditionApplied, slowed_on, until=When.ENCOUNTER, on=me, label=f"{c.ref} on")
    c.watch(ConditionEnded, slowed_off, until=When.ENCOUNTER, on=me, label=f"{c.ref} off")


@power(
    "m6609a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m6609a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6609a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m6609a3(c: Cast) -> None:
    """A rampage through the line, approximated the same way m5338a1's is:
    it moves its full speed and claws at enemies it ends up passing
    adjacent to along the way."""
    speed = c.speed_of()
    struck: set[int] = set()
    for _ in range(speed):
        c.shift(1, share=True)
        for foe in _adjacent_foes(c):
            if foe not in struck:
                struck.add(foe)
                _struck(c, "m6609a2", 1, foe)


@power(
    "m6609a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6609a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    area = spread({c.here}, 2)
    c.zone(area, blocks_sight=True, until=When.EONT, label=c.ref)


def _ring_radius(c: Cast) -> int:
    for _, zone in c.world.zones.all():
        if zone.owner == c.me and zone.label == "m6609a0" and zone.aura is not None:
            return zone.aura
    return 0


def _not_yet_widened(c: Cast, ev: TurnStart) -> bool:
    return ev.actor == c.me and not ev.ghost and _ring_radius(c) < 5


def _fully_widened(c: Cast, ev: TurnStart) -> bool:
    return ev.actor == c.me and not ev.ghost and _ring_radius(c) >= 5


@power(
    "m6609a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6609a5(c: Cast) -> None:
    """Recharges on its own printed condition -- aura still under 5 -- rather
    than only a die; the ring is widened by mutating the aura's own radius,
    the same way m5730a0 flags a zone difficult by hand."""
    _recharge_on(c, TurnStart, lambda ev: _not_yet_widened(c, ev))
    for _, zone in c.world.zones.all():
        if zone.owner == c.me and zone.label == "m6609a0" and zone.aura is not None:
            zone.aura = min(5, zone.aura + 2)
            return


@power(
    "m6609a6",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 7),
)
def m6609a6(c: Cast) -> None:
    _recharge_on(c, TurnStart, lambda ev: _fully_widened(c, ev))
    if c.strike():
        c.hit()
        c.prone(on=c.target)
        c.condition(
            Condition.PINNED, until=When.SAVE_ENDS, on=c.target, ongoing=(5, DamageType.UNTYPED)
        )
    if c.last:
        for _, zone in c.world.zones.all():
            if zone.owner == c.me and zone.label == "m6609a0" and zone.aura is not None:
                zone.aura = 1


# --------------------------------------------------------------------------
# m943
# --------------------------------------------------------------------------


@power(
    "m943a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m943a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m943a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 4),
)
def m943a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m943a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m943a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    c.shift(1)


@power("m943a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m943a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_granting_ca
    )
