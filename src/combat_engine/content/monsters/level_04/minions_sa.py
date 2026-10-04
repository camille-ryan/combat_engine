"""Monster abilities, level 4, minions.

Fourteen stat blocks, twenty-seven rows. The conventions are the ones the
level-1 to level-3 sweeps settled and are not restated here beyond the two
that this batch leans on hardest:

* a minion's flat damage goes in the header as `Damage("", n, kind=MINION)`
  and the body calls `c.hit()`, so an MM1 block can be rescaled later;
* a card printing **two** numbers for one blow -- "5 damage (6 damage if it
  has combat advantage)" -- keeps the base in the header where a rescale can
  find it and adds the difference in the body with `c.flat`. Putting the
  whole conditional in the body would take the number out of the data; a
  gated `c.bonus` would survive the turn, and these are per-swing lines.

Nine helpers are imported rather than copied, from the level-1, level-2 and
level-3 sweeps. A card that prints no range at all is melee 1, and a printed
band of "15/30" takes the normal range.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _beside_kin
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.soldiers_sa import _missed_me_in_melee
from combat_engine.content.monsters.level_03.artillery import _save_ends
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Relation,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    ConditionApplied,
    Dropped,
    Hit,
    Miss,
    MoveStart,
    RelationCleared,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import adjacent, enemies, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _extra_with_advantage(c: Cast, more: int) -> None:
    """The second number on a blow that reads "5 damage (6 with advantage)".

    Read off `c.result` rather than asked of the board again: a one-shot
    grant is already spent by the time the blow is rolled, so
    `has_combat_advantage` comes back false exactly when the card pays.
    """
    if c.result is not None and c.result.advantage:
        c.flat(more)


def _while_gripped(c: Cast, victim: int, *held: Effect | None) -> None:
    """End every hold a grab carries the moment the victim gets out.

    `_until_escape` next door does this for one effect under a fixed label;
    this grab prints three clauses with one lifetime, and three watches under
    the same label is three chances to end the wrong one.
    """
    live = [e for e in held if e is not None]
    if not live:
        return

    def freed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.target == victim:
            while live:
                c.world.effects.end(live.pop(), "it escaped")

    c.watch(
        RelationCleared, freed, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} grip",
    )


def _ally_struck_beside_me(world: World, me: int, ev: Any) -> bool:
    """"An ally hits an enemy adjacent to it."

    Neither `ally_within` nor `enemy_target_within` asks this: the first reads
    the attacker's distance from me and the second wants the other side, and
    the printed sentence measures the **victim's** distance while demanding
    the attacker be a friend.
    """
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if who is None or victim is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    return victim in enemies(world, me) and adjacent(world, me, victim)


def _bloodied_neighbour_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """"A bloodied enemy adjacent to it shifts."

    `MoveStart` and not `MoveEnd`: by the end of a shift the enemy has gone
    and `adjacent` is false precisely when the row should fire. `kind_` is set
    on every emission even though the dataclass does not declare it.
    """
    from combat_engine.engine.components import Health

    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "kind_", "") != "shift":
        return False
    if who not in enemies(world, me) or not adjacent(world, me, who):
        return False
    hp = world.get(who, Health)
    return hp is not None and hp.bloodied


# --------------------------------------------------------------------------
# m3503
# --------------------------------------------------------------------------


@power(
    "m3503a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 7, kind=MINION),
)
def m3503a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M3503_HIT = "the creature hits with a melee attack"


@power(
    "m3503a1",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3503_HIT,
    on=Trigger(Hit, both(by_me, by_melee), _M3503_HIT),
)
def m3503a1(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3561
# --------------------------------------------------------------------------


@power(
    "m3561a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 5, kind=MINION),
)
def m3561a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _extra_with_advantage(c, 1)


@power(
    "m3561a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 5, kind=MINION),
)
def m3561a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M3561_MISSED = "a melee attack misses the creature"


@power(
    "m3561a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3561_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M3561_MISSED),
)
def m3561a2(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3640
# --------------------------------------------------------------------------


@power(
    "m3640a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 5, kind=MINION),
)
def m3640a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4118
# --------------------------------------------------------------------------


@power(
    "m4118a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, kind=MINION),
)
def m4118a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4118a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 4, kind=MINION),
)
def m4118a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4118a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4118a2(c: Cast) -> None:
    """A gate on the damage context, which carries `advantage`, rather than a
    hold put on and taken off around each swing."""
    c.bonus(
        "damage",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# --------------------------------------------------------------------------
# m4415
# --------------------------------------------------------------------------


@power(
    "m4415a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, dtype=DamageType.ACID, kind=MINION),
)
def m4415a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4415_DOWN = "the creature drops to 0 hit points"


@power(
    "m4415a1",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_CREATURE,
    keywords=[Keyword.HEALING, Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("", 5, dtype=DamageType.POISON, kind=MINION),
    trigger=_M4415_DOWN,
    on=Trigger(Dropped, about_me, _M4415_DOWN),
    dropped=("Target.kind",),
)
def m4415a1(c: Cast) -> None:
    """The attack half spares its own sort and the Effect half heals them, so
    the burst takes every creature and the type word decides which branch each
    one is in. `Target` filters on side, count and size and has nothing to say
    about what a creature *is*, which is the dropped clause: the offer is not
    narrowed even though the body is.

    The caster is left out of the healing. It is a plant and it is on 0 hit
    points, so the printed line would otherwise bring it back up.
    """
    victim = c.target
    if victim is None:
        return
    if c.is_kind("plant", on=victim):
        if victim != c.me:
            c.heal(5, on=victim)
        return
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4533
# --------------------------------------------------------------------------


@power(
    "m4533a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, dtype=DamageType.FIRE, kind=MINION),
)
def m4533a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4533_DOWN = "the creature drops to 0 hit points"


@power(
    "m4533a1",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    damage=Damage("", 5, dtype=DamageType.FIRE, kind=MINION),
    trigger=_M4533_DOWN,
    on=Trigger(Dropped, about_me, _M4533_DOWN),
)
def m4533a1(c: Cast) -> None:
    """No attack line is printed, so the burst simply lands -- `c.hit()` with
    no strike above it applies the header's damage to each creature caught."""
    c.hit()


_M4533_MISSED = "a fire attack misses the creature"


@power(
    "m4533a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M4533_MISSED,
    on=Trigger(Miss, both(targets_me, by_keyword(Keyword.FIRE)), _M4533_MISSED),
)
def m4533a2(c: Cast) -> None:
    c.teleport(7)


# --------------------------------------------------------------------------
# m5381
# --------------------------------------------------------------------------


@power(
    "m5381a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 6, kind=MINION),
)
def m5381a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5381a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("", 6, kind=MINION),
)
def m5381a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5381a2",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5381a2(c: Cast) -> None:
    """The flight is lent for the length of the move: the block has no fly
    mode of its own, and `c.move(at="fly")` measures the mode rather than the
    ground speed, so without the grant the pathfinder walks it."""
    c.mode("fly", 5, until=When.EOT, on=c.me)
    c.move(5, at="fly")


# --------------------------------------------------------------------------
# m5406
# --------------------------------------------------------------------------


@power(
    "m5406a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5406a0(c: Cast) -> None:
    """"While at least one other of its own sort with this trait is adjacent."
    The ref is the only thing an author is given to compare, and every one of
    them arms the trait, so carrying it is the same question as being one."""
    kin = _ref_of(c, c.me)
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: _beside_kin(c, kin)
    )


@power(
    "m5406a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 4, kind=MINION),
)
def m5406a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5406_SAVE = "the creature suffers an effect that a save can end"


@power(
    "m5406a2",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5406_SAVE,
    on=Trigger(ConditionApplied, both(targets_me, _save_ends), _M5406_SAVE),
)
def m5406a2(c: Cast) -> None:
    """The header says free action and the Effect line says immediate
    reaction; the Effect line is the one the rules read.

    `c.save()` takes whichever save-ends effect it finds first and the printed
    line is specifically the triggering one, so the hold is picked out by the
    condition the event named.
    """
    condition = getattr(c.trigger, "condition", None)
    if condition is None:
        c.save(on=c.me)
        return
    for eff in list(c.world.effects.of(c.me)):
        if condition in eff.conditions:
            c.world.effects.save(eff)
            return
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m5412
# --------------------------------------------------------------------------


@power(
    "m5412a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, kind=MINION),
)
def m5412a0(c: Cast) -> None:
    """`c.charge` is the question the parenthetical asks; the extra point rides
    on top of the header's number rather than replacing it."""
    if c.strike():
        c.hit()
        if c.charge:
            c.flat(1)


@power(
    "m5412a1",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5412a1(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m5488
# --------------------------------------------------------------------------


@power(
    "m5488a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 6, kind=MINION),
)
def m5488a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _extra_with_advantage(c, 1)


_M5488_ALLY_HIT = "an ally hits an enemy adjacent to the creature"


@power(
    "m5488a1",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5488_ALLY_HIT,
    on=Trigger(Hit, _ally_struck_beside_me, _M5488_ALLY_HIT),
)
def m5488a1(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m6362
# --------------------------------------------------------------------------


@power(
    "m6362a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("", 6, kind=MINION),
    dropped=("c.grab(dc=)",),
)
def m6362a0(c: Cast) -> None:
    """Three clauses with one lifetime -- the hold on the victim, the burn it
    takes each turn, and the creature's own inability to swing while it holds
    on -- all end when the grab does, which no `When` measures.

    The printed escape DC is the dropped half: `c.grab` sets the relation and
    `c.escape` rolls against the holder's own numbers, so a card naming a
    number has nowhere to put it.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab()
    _while_gripped(
        c,
        victim,
        c.penalty("attack", 2, on=victim, until=When.ENCOUNTER),
        c.ongoing(6, on=victim, until=When.ENCOUNTER),
        c.cannot_attack(on=c.me, until=When.ENCOUNTER),
    )


# --------------------------------------------------------------------------
# m6607
# --------------------------------------------------------------------------


@power(
    "m6607a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, kind=MINION),
)
def m6607a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(2)


_M6607_SHIFT = "a bloodied enemy adjacent to the creature shifts"


@power(
    "m6607a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6607_SHIFT,
    on=Trigger(MoveStart, _bloodied_neighbour_shifts, _M6607_SHIFT),
)
def m6607a1(c: Cast) -> None:
    """The printed line names the row to use, so it is used rather than a
    basic attack: `c.use_power` leaves its roll in `c.result`, which is what
    the swing's own riders read back."""
    who = getattr(c.trigger, "actor", None)
    if who is not None:
        c.use_power("m6607a0", on=who)
