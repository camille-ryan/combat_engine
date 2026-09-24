"""Monster abilities, level 7: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=12)` and `Damage("2d6", 10)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Several rows here are filed under an action heading and are plainly traits;
those are declared `ActionType.NONE` and armed once when the fight starts.
A printed range of "10/20" takes the short range, which is what the creature
can actually shoot without a penalty the engine does not model.

Two shapes recur at this tier and are written once at the top: an aura whose
occupants carry a hold while they are inside it, and a printed "crit NdX + n"
line, which replaces the damage rather than adding to it.

One thing the levels below did not need is a **charge made from inside a
body**: `actions.perform` builds one out of a walk plus `use(..., charge=True)`,
and a row whose printed Effect *is* the charge has to do the same, because the
flag is what puts `charge` on the attack events and in both modifier contexts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Event,
    Health,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    Bloodied,
    DamageApplied,
    Hit,
    Miss,
    PowerUsed,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.movement import walk
from combat_engine.engine.query import (
    alive,
    creatures,
    distance_between,
    enemies,
    flanked_by,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_charge, by_melee

#: The reaches that count as a melee attack, for the rows whose rider is on
#: "its melee attacks" rather than on one named row.
MELEE_KINDS = ("melee",)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)

#: What a printed "living creature" rules out. The engine holds no flag for
#: being alive, so the question is put to the type line the way `c.is_kind`
#: reads it.
LIFELESS = ("undead", "construct")


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _living(c: Cast, who: int) -> bool:
    return not any(c.is_kind(word, on=who) for word in LIFELESS)


def _melee_ctx(ctx: dict[str, Any]) -> bool:
    """Is the attack this modifier is being read for a melee one?

    The attack context carries `ranged`; the damage context does not, and a
    gate on a key the context has no entry for is silently false. Both carry
    the row's ref, so the reach is looked up from that instead.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach_of(ctx.get("branch", 0)).kind in MELEE_KINDS


def _crit_line(c: Cast, dice: str, bonus: int) -> None:
    """A printed "crit NdX + n" line.

    It *replaces* the damage rather than adding to it, and it is a roll --
    so it is applied flat, past the engine's own rule that a critical maxes
    the declared dice, which would read the wrong number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus)
    else:
        c.hit()


def _crowded(c: Cast, who: int, count: int) -> bool:
    """Is that creature hemmed in by `count` or more of the caster's allies?

    The caster is left out of the tally every time: every printed line of
    this shape counts *its allies*, and the `ally` pool puts the creature
    itself in.
    """
    return sum(1 for a in c.within(1, of=who, side="ally") if a != c.me) >= count


def _aura(
    c: Cast,
    radius: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
) -> int:
    """An aura whose occupants carry a hold for as long as they are inside.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the hold should go on and
    come off. Whoever is already standing inside is caught at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(radius, until=When.ENCOUNTER)

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        take(actor)
    return ring


def _bites(c: Cast, ring: int, dice: str, dtype: DamageType) -> None:
    """An aura that hurts whoever enters it or starts a turn in it.

    Not `c.burns`, which takes a flat number: the printed line is a die, so
    the two moments are watched by hand and rolled each time. Once per round
    per creature, which is what `c.burns` does and what the printed line
    means by naming two occasions rather than every step. The owner is left
    out of its own aura, as the general rule has it.
    """
    me, struck = c.me, {}

    def bite(who: int) -> None:
        if who == me or struck.get(who) == c.world.round or not alive(c.world, who):
            return
        struck[who] = c.world.round
        c.damage(dice, dtype=dtype, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")


def _run_at(c: Cast, victim: int) -> bool:
    """Walk into reach of a named creature, the way a charge's move does.

    `c.move` picks its own destination through the decider, which is right
    for "it moves" and useless for "it charges that one" -- so the path is
    chosen here, shortest first, exactly as `actions._charges` chooses one.
    """
    beside = spread(squares(c.world, victim), 1)
    paths = c.world.reachable_paths(c.me, c.speed_of())
    best = min(
        (
            (len(path), dest, path)
            for dest, path in paths.items()
            if dest in beside and path
        ),
        default=None,
    )
    if best is not None:
        walk(c.world, c.me, list(best[2]))
    return c.adjacent(victim)


# ==========================================================================
# Brutes
# ==========================================================================

# -- m105 -------------------------------------------------------------------


@power(
    "m105a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m105a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means.

    Only the burn is printed as acid; the declared line is untyped, so the
    header carries no type and the ongoing names one.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m105a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m105a1(c: Cast) -> None:
    """A burst with no damage line at all: the whole of it is the penalty.

    "Deafened creatures are immune" is a per-target exemption no `Target` can
    say, so the body drops them before the roll rather than after it.
    """
    if c.target is None or c.is_(Condition.DEAFENED):
        return
    if c.strike():
        c.penalty("attack", 2, until=When.EONT)


_M105_BLED = "the m105 is first bloodied"


@power(
    "m105a2",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    damage=Damage("2d8", dtype=DamageType.ACID, kind=LIMITED),
    trigger=_M105_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M105_BLED),
)
def m105a2(c: Cast) -> None:
    """A splash that hits automatically, so no attack is declared.

    The filed line carries two readings on top of each other -- an attack
    against a defence the row does not name, and "automatic hit" -- and only
    the second is a whole sentence. The automatic one is taken, which is also
    the only one that can be written: a roll needs a defence to be against.

    "First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. The card prints a burst and no target line, so the
    burst takes the enemies standing in it rather than everybody.
    """
    c.hit()
    c.ongoing(5, DamageType.ACID)


@power(
    "m105a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m105a3(c: Cast) -> None:
    """A rolled extra, so a watch rather than a gated `c.bonus`: a modifier
    is a number and this one is a die.

    It rides the `Hit`, which is announced before the damage of the blow it
    belongs to lands, so the two arrive together. Who is crowding the victim
    changes every time anything moves, so the count is taken then and not
    stored.
    """
    me = c.me

    def press(ev: Hit) -> None:
        if ev.attacker != me or ev.target not in c.enemies():
            return
        if _crowded(c, ev.target, 2):
            c.damage("1d6", on=ev.target)

    c.watch(Hit, press, until=When.ENCOUNTER, on=me, label="m105a3")


@power(
    "m105a4",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m105a4(c: Cast) -> None:
    """An aura 1, with the opening held per occupant.

    "All other creatures" is wider than any argument `c.grants_advantage`
    takes -- it offers the caster, one named ally, or the caster's side --
    so the relation is laid by hand, once per beneficiary, on the one hold
    that ends when the enemy walks out of reach. The m105 itself is left
    out, which is what "other" means here.

    The printed qualifier "when making melee attacks" has nowhere to go:
    `GRANTS_CA_TO` is a fact about two creatures and `has_combat_advantage`
    is not told what is being swung. See the report.
    """
    me = c.me

    def hold(who: int) -> Effect | None:
        others = [
            e for e in creatures(c.world) if e not in (me, who) and alive(c.world, e)
        ]
        if not others:
            return None
        return c.world.effects.apply(
            who,
            me,
            When.ENCOUNTER,
            label=f"{c.ref} opening",
            relations=[(Relation.GRANTS_CA_TO, who, b) for b in others],
        )

    _aura(c, 1, lambda who: who in c.enemies(), hold)


# -- m252 -------------------------------------------------------------------


@power(
    "m252a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m252a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m252a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m252a1(c: Cast) -> None:
    """Flanking is recomputed rather than stored, and it changes with every
    step either creature takes -- so the gate is read at the moment of the
    roll. `flanked_by` asks about the target first and the flanker second."""
    me = c.me

    def pinning(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and flanked_by(c.world, who, me)

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=pinning)


# -- m253 -------------------------------------------------------------------


@power(
    "m253a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m253a0(c: Cast) -> None:
    """Two clauses on one condition, and they need different machinery.

    "-2 to all defences" is four modifiers, gated rather than applied once:
    hit points cross back and forth, and a defence is read again after the
    roll has been announced. The additional move action is the budget
    itself, handed over at the start of the turn -- `Encounter._begin`
    refreshes the budget and *then* emits `TurnStart`, so a listener there
    is adding to a fresh turn rather than to the leavings of the last one.
    """
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.penalty(d, 2, until=When.ENCOUNTER, on=me, when=hurt)

    def spare(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.bloodied(me):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.move += 1

    c.watch(TurnStart, spare, until=When.ENCOUNTER, on=me, label="m253a0")


def _rider_charged(c: Cast, ev: Event) -> bool:
    """Did the creature in this one's saddle just charge something?

    Three questions, because each is separate: who is riding, whose side
    that creature is on, and whether the blow was a charge -- which is what
    `charge` on the attack event is for. No level is printed here, unlike
    the mounts a tier below, so none is asked.
    """
    rider = getattr(ev, "attacker", None)
    if rider is None or rider not in c.world.relations.targets(Relation.RIDDEN_BY, c.me):
        return False
    if team(c.world, rider) is not team(c.world, c.me):
        return False
    return by_charge(c.world, c.me, ev)


@power(
    "m253a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m253a1(c: Cast) -> None:
    """Filed as a trait, and it is one: the free action it grants is not a
    row anybody chooses but a rider on what the creature in the saddle did.

    Both `Hit` and `Miss` are watched. The printed trigger is the rider's
    charge and the printed moment is *after* its melee basic attack, so the
    answer is owed whether or not that attack landed, and those two events
    are the only places the resolved swing can be read from.

    The row that prints the claw is used rather than copied, so its damage
    line stays in one place, and the victim is read off the trigger: it is
    the rider's target, not this creature's.
    """
    me = c.me

    def answer(ev: Event) -> None:
        if not _rider_charged(c, ev):
            return
        victim = getattr(ev, "target", None)
        for _ in range(2):
            if victim is None or not alive(c.world, victim):
                return
            use(c.world, me, "m253a2", targets=[victim], spend=False)

    c.watch(Hit, answer, until=When.ENCOUNTER, on=me, label="m253a1 hit")
    c.watch(Miss, answer, until=When.ENCOUNTER, on=me, label="m253a1 miss")


@power(
    "m253a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 10),
)
def m253a2(c: Cast) -> None:
    """"+14 while bloodied" is the printed line plus two rather than a second
    attack line, so it is rolled as a plus and the header keeps the number
    the engine takes the level term out of."""
    if c.strike(plus=2 if c.bloodied(c.me) else 0):
        c.hit()


# -- m268 -------------------------------------------------------------------


@power(
    "m268a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m268a0(c: Cast) -> None:
    """An aura 3 for the board to draw, biting on entry and on a turn begun
    inside it. The printed line is about any creature at all, either side."""
    _bites(c, c.aura(3, until=When.ENCOUNTER), "1d8", DamageType.FIRE)


@power(
    "m268a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE),
)
def m268a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m268a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m268a2(c: Cast) -> None:
    """The printed target is "creatures in the blast", which is both sides."""
    if c.strike():
        c.hit()


# -- m2853 ------------------------------------------------------------------


@power(
    "m2853a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 6),
)
def m2853a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 18)


@power(
    "m2853a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6),
)
def m2853a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m2853a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 6, kind=LIMITED),
)
def m2853a2(c: Cast) -> None:
    """A zone that stays centred on its maker is an aura and nothing else:
    `c.zone` fixes its squares where they were laid, and the printed line
    says this one moves.

    The Effect is once for the whole power rather than once per target, so
    it is guarded with `c.first` -- and it happens on a miss too, which is
    what an Effect line means.
    """
    if c.first:
        me = c.me
        ring = c.aura(1, until=When.EONT)

        def howl(ev: TurnStart) -> None:
            if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
                return
            if ev.actor in c.world.zones.occupants(ring):
                c.flat(5, on=ev.actor)

        c.watch(TurnStart, howl, until=When.EONT, on=me, label="m2853a2")
    if c.target is not None and c.strike():
        c.hit()


@power(
    "m2853a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2853a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


# -- m2974 ------------------------------------------------------------------


@power(
    "m2974a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2974a0(c: Cast) -> None:
    """A gated damage modifier, so the extra rides the blow it belongs to and
    meets the same resistance.

    No reach gate: the printed line is "the m2974's attacks", not its melee
    attacks. The target being an enemy *is* gated, because the creature also
    has a row that damages one of its own allies and that is not an attack.
    """
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who in c.enemies() and _crowded(c, who, 2)

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=mobbed)


@power(
    "m2974a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 8),
)
def m2974a1(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("3d6", 10)
    else:
        c.hit()


@power(
    "m2974a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m2974a2(c: Cast) -> None:
    """An Effect line with no attack roll in it: the ally simply bleeds and
    the m2974 drinks it."""
    if c.target is None:
        return
    c.flat(5)
    c.heal(5, on=c.me)


# -- m2997 ------------------------------------------------------------------


@power(
    "m2997a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 8),
)
def m2997a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 20)


_M2997_BLED = "the m2997 is first bloodied"


@power(
    "m2997a1",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M2997_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2997_BLED),
)
def m2997a1(c: Cast) -> None:
    """The row that prints the axe is used rather than copied, so its damage
    and its critical line stay in one place.

    Declared with no target: `Bloodied` names nobody but the creature it is
    about, so the dispatcher would aim this at the m2997 itself. Whoever is
    standing next to it is the one that gets the answer -- the creature that
    drew the blood need not be in reach, or even alive.
    """
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is not None:
        use(c.world, c.me, "m2997a0", targets=[who], spend=False)


@power(
    "m2997a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d12", 2, kind=LIMITED),
    requires=_is_bloodied,
    requires_text="the m2997 must be bloodied",
)
def m2997a2(c: Cast) -> None:
    """The healing is printed on the hit rather than as an Effect, so a miss
    buys nothing."""
    if c.strike():
        c.hit()
        c.heal(10, on=c.me)


@power(
    "m2997a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2997a3(c: Cast) -> None:
    """A rolled extra and a fixed drink, both hung on the `Hit`.

    The die cannot ride a `c.bonus`, which is a number; and whether the
    target was already bleeding is read where the hit is announced, which is
    before the blow's own damage lands -- so a swing never pays itself the
    bonus for the wound it is in the middle of making.
    """
    me = c.me

    def drink(ev: Hit) -> None:
        if ev.attacker != me or not c.bloodied(ev.target):
            return
        c.damage("1d6", on=ev.target)
        c.heal(5, on=me)

    c.watch(Hit, drink, until=When.ENCOUNTER, on=me, label="m2997a3")


_M2997_BLOW = "the m2997 damages an enemy"


def _damaged_a_foe(world: World, me: int, ev: DamageApplied) -> bool:
    """Sides are compared directly rather than through `enemies`, which
    filters out the dead -- and damage is exactly what kills people, so
    asking that way would have made the killing blow silently not count."""
    if ev.source != me or ev.amount <= 0:
        return False
    theirs = team(world, ev.target)
    return theirs is not None and theirs is not team(world, me)


@power(
    "m2997a4",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2997_BLOW,
    on=Trigger(DamageApplied, when=_damaged_a_foe, text=_M2997_BLOW),
)
def m2997a4(c: Cast) -> None:
    """More of the blow that has just landed, so the victim is read off the
    trigger rather than aimed at: the beneficiary of this row is the m2997
    and a row declaring a target would be pointed at the wrong end of it.

    `DamageApplied` and not `Hit`: the printed word is "damages", which an
    ongoing burn and an attack that got through resistance both are, and a
    hit that came to nothing is not.
    """
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.damage("1d10", on=who)


# -- m3093 ------------------------------------------------------------------


@power(
    "m3093a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3093a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the penalty held per occupant."""
    _aura(
        c,
        1,
        lambda who: who in c.enemies() and _living(c, who),
        lambda who: c.penalty("attack", 2, until=When.ENCOUNTER, on=who),
    )


@power(
    "m3093a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d6", 5),
)
def m3093a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3093a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 2),
)
def m3093a2(c: Cast) -> None:
    """One creature or two, and against a single one the declared line is
    rolled twice -- the row's own attack made again rather than the row used
    again, which is what keeps it one standard action.

    "If this attack bloodies the target" is the crossing and not the state,
    so whether the creature was already bleeding is read before the blow and
    compared with after it. The follow-up goes through the row that prints
    it, so that damage line stays in one place.
    """
    who = c.target
    if who is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, who):
            return
        was = c.bloodied(who)
        if not c.strike(on=who):
            continue
        c.hit(on=who)
        if not was and alive(c.world, who) and c.bloodied(who):
            use(c.world, c.me, "m3093a1", targets=[who], spend=False)


# -- m3104 ------------------------------------------------------------------


def _m3104_recharge(c: Cast) -> None:
    """"Recharges after it hits two or more targets with m3104a2".

    The database files a plain 6+ where the stat block prints a sentence.
    The number stays in the header, because that is what `actions.recharge`
    rolls and what the card shows; this is the printed sentence on top of
    it, and the two only ever agree to make the row available sooner.

    Two or more *targets of one use*, so the tally is emptied by the
    `PowerUsed` that opens each one -- `Cast.used` announces it before the
    body runs for the first target, so the reset is always in front of the
    hits it is counting. Armed from the body, which is all that is needed:
    the row has to have been spent before there is anything to give back.
    """
    me, label = c.me, "m3104a1 recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    hits: set[int] = set()

    def fresh(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m3104a2":
            hits.clear()

    def tally(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3104a2":
            return
        hits.add(ev.target)
        if len(hits) >= 2:
            known = c.world.get(me, Powers)
            if known is not None:
                known.restore("m3104a1")

    c.watch(PowerUsed, fresh, until=When.ENCOUNTER, on=me, label=label)
    c.watch(Hit, tally, until=When.ENCOUNTER, on=me, label=f"{label} hits")


@power(
    "m3104a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m3104a0(c: Cast) -> None:
    """The splash is a flat number against a second creature and no part of
    the declared line, so it is dealt by hand -- and it is printed on the
    hit, so a miss buys nothing."""
    if not c.strike():
        return
    _crit_line(c, "1d8", 14)
    other = next((f for f in sorted(c.within(1, side="enemy")) if f != c.target), None)
    if other is not None:
        c.flat(4, on=other)


@power(
    "m3104a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 9, kind=LIMITED),
)
def m3104a1(c: Cast) -> None:
    """A charge with its own attack line in place of the basic one.

    `actions.perform` builds a charge out of a walk plus `use(...,
    charge=True)`, and a row whose printed Effect *is* the charge does the
    same from inside the body. The flag is raised on the cast rather than
    passed to `use`, because the row making the charge is this one: it is
    what puts `charge` on the attack events and in both modifier contexts,
    which is what every charge rider reads.

    "+3 to AC during the charge" goes on before the run, so it covers the
    opportunity attacks the approach draws. A charge ends the turn whatever
    is left of it, so the end of the turn is where the bonus comes off.
    """
    victim = c.target
    if victim is None:
        return
    _m3104_recharge(c)
    c.bonus(Defense.AC, 3, until=When.EOT, on=c.me)
    c.charge = True
    _run_at(c, victim)
    if c.strike(on=victim):
        _crit_line(c, "2d8", 25)


@power(
    "m3104a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m3104a2(c: Cast) -> None:
    """"Miss: 4 damage" is a flat number rather than half the line, so it is
    dealt by hand and not through `c.hit(half=True)`."""
    if c.strike():
        _crit_line(c, "1d8", 14)
    else:
        c.flat(4)


@power(
    "m3104a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3104a3(c: Cast) -> None:
    """Who is standing beside the victim changes every time anything moves,
    so the gate is read at the moment of the roll rather than stored."""
    me = c.me

    def beside(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return _crowded(c, who, 1)

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=beside)


@power(
    "m3104a4",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3104a4(c: Cast) -> None:
    """Temporary hit points cannot ride a modifier, so this hangs off the
    `Hit` -- and `by_melee` reads the reach off the row that landed it,
    which is the only thing on the event that says melee."""
    me = c.me

    def plate(ev: Hit) -> None:
        if ev.attacker == me and by_melee(c.world, me, ev):
            c.temp_hp(4, on=me)

    c.watch(Hit, plate, until=When.ENCOUNTER, on=me, label="m3104a4")


@power(
    "m3104a5",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m3104a5(c: Cast) -> None:
    """The saving throw is against an ongoing damage effect specifically, and
    `c.save` does not choose between them -- it takes the first save-ends
    hold it finds, which might be a daze. So the burning one is picked here
    and shaken by hand.

    Being bloodied is read before anything is given, which is what "if it
    uses this power while bloodied" asks.
    """
    me = c.me
    hurt = c.bloodied(me)
    c.temp_hp(6, on=me)
    burning = next(
        (e for e in c.world.effects.of(me) if e.when is When.SAVE_ENDS and e.ongoing),
        None,
    )
    if burning is not None:
        c.world.effects.save(burning)
    if hurt:
        c.heal(6, on=me)


# -- m358 -------------------------------------------------------------------


@power(
    "m358a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 5),
)
def m358a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 17)


@power(
    "m358a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="the m358 must be bloodied",
)
def m358a1(c: Cast) -> None:
    """A basic attack rather than a named row: `c.basic` swings whatever this
    creature's basic actually is, which for a monster is one of its own rows.

    The surge and the number are two printed clauses and not one: 36 is not
    a quarter of this creature's maximum, so `c.surge` would heal the wrong
    amount. The surge is spent for nothing and the healing given flat.
    """
    if c.target is not None:
        c.basic(on=c.target)
    c.spend_surge(on=c.me)
    c.heal(36, on=c.me)


_M358_STRUCK = "an adjacent enemy hits the m358"


def _hit_by_neighbour(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.target == me
        and ev.attacker != me
        and ev.attacker in enemies(world, me)
        and distance_between(world, me, ev.attacker) <= 1
    )


@power(
    "m358a2",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M358_STRUCK,
    on=Trigger(Hit, when=_hit_by_neighbour, text=_M358_STRUCK),
)
def m358a2(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher
    points a triggered row at the creature the event names as its target,
    and on a `Hit` against the m358 that is the m358 itself."""
    who = getattr(c.trigger, "attacker", None)
    if who is not None:
        c.basic(on=who)


@power(
    "m358a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m358a3(c: Cast) -> None:
    """The extra is a flat number, so it rides a gated damage modifier and
    meets the same resistance as the blow it belongs to. The healing cannot
    ride one, so it hangs off the `Hit` -- read there, before the blow's own
    damage lands, so both halves answer the same question about the victim.
    """
    me = c.me

    def bleeding(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who in c.enemies() and c.bloodied(who)

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=bleeding)

    def drink(ev: Hit) -> None:
        if ev.attacker == me and ev.target in c.enemies() and c.bloodied(ev.target):
            c.heal(5, on=me)

    c.watch(Hit, drink, until=When.ENCOUNTER, on=me, label="m358a3")


# -- m5015 ------------------------------------------------------------------


@power(
    "m5015a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m5015a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5015a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m5015a1(c: Cast) -> None:
    """Two uses of the row that prints the attack, so its damage line stays
    in one place.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is bitten twice.
    That is the only reading that loses nothing: a header fixed at one
    creature could not offer the split, and one fixed at two could not offer
    the double.
    """
    who = c.target
    if who is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, who):
            return
        use(c.world, c.me, "m5015a0", targets=[who], spend=False)


@power(
    "m5015a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("3d8", dtype=DamageType.PSYCHIC),
)
def m5015a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5015a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
)
def m5015a3(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the condition."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)
