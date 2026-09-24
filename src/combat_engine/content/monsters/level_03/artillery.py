"""Monster abilities, level 3: the artillery.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=8)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage.

Two things this file had to settle that level 2 never met.

**Damage of two types.** `Damage(dtype=...)` holds one, and two rows here
print "cold and lightning" and "fire and thunder". Both keywords go in
`keywords`, so anything reading the kind of attack it was still sees both;
the header keeps the first printed type, which is what the resistance check
reads. See the report: the field wants a set.

**"Includes an ally in the blast or burst."** A modifier's gate is handed
the attacker, the target and the power ref, and never the rest of the
targets -- so who else the burst caught cannot be asked there. `PowerUsed`
carries the whole list and is emitted before the first roll, so the trait
watches that and the gate only has to ask which power is being rolled.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_01.skirmishers import wary_of_traps
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
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
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.events import (
    ConditionApplied,
    Hit,
    Miss,
    PowerUsed,
    RelationCleared,
    SurgeSpent,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.triggers import Trigger, both, targets_me

#: The ranges a printed "ranged or area attack" means, and the ones a
#: "blast or burst" means. Asked off the power in the registry, because a
#: modifier's context carries the ref and not the range.
_FROM_AFAR = ("ranged", "area_burst")
_SPREADS = ("close_blast", "close_burst", "area_burst")


def _reach_of(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None else ""


# --------------------------------------------------------------------------
# m273
# --------------------------------------------------------------------------


@power(
    "m273a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m273a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m273a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m273a1(c: Cast) -> None:
    """Marks a target for one friend's next shot.

    "Its next ranged attack roll against the same target" is the `once`
    flag and the gate together: `once` spends the bonus on the first roll
    that could use it, and the gate keeps it to shots at this creature.
    The printed range of 20/40 is written as its normal band -- `Range`
    holds one number and the engine has no -2 to apply.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    friend = c.choose(sorted(mates), "an ally lines up the same shot")
    if friend is None:
        return
    c.bonus(
        "attack",
        2,
        on=friend,
        until=When.ENCOUNTER,
        once=True,
        when=lambda ctx: ctx.get("target") == victim
        and _reach_of(ctx.get("power", "")) == "ranged",
    )


def _save_ends(world: object, me: int, ev: ConditionApplied) -> bool:
    """Was the thing just applied one a save can end?

    `ConditionApplied` carries the duration as the printed word, which is
    the only place the distinction between "save ends" and a clocked
    effect is readable from outside `durations`.
    """
    return getattr(ev, "duration", "") == When.SAVE_ENDS.value


_TAKES_A_SAVE_ENDS_EFFECT = "the m273 is subjected to an effect that a save can end"


@power(
    "m273a2",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    trigger=_TAKES_A_SAVE_ENDS_EFFECT,
    on=Trigger(
        ConditionApplied,
        when=both(targets_me, _save_ends),
        text=_TAKES_A_SAVE_ENDS_EFFECT,
    ),
    reach=PERSONAL,
    target=SELF,
)
def m273a2(c: Cast) -> None:
    """Shrug it off at once, before it has had a turn to bite.

    The stat block's header says free action and the Effect line says
    immediate reaction; the Effect line is the one the rules read, so that
    is the action type. Both land in the same window either way.

    `c.save()` takes whichever save-ends effect it finds first, and the
    printed line is specifically the triggering one -- so the effect is
    picked out by the condition the event named and rolled against
    directly. A creature already carrying something else would otherwise
    shake off the wrong one.
    """
    condition = getattr(c.trigger, "condition", None)
    if condition is None:
        c.save()
        return
    mine = [
        e
        for e in c.world.effects.of(c.me)
        if e.when is When.SAVE_ENDS and condition in e.conditions
    ]
    if mine:
        c.world.effects.save(mine[-1])


# --------------------------------------------------------------------------
# m2824
# --------------------------------------------------------------------------


@power(
    "m2824a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m2824a0(c: Cast) -> None:
    """An aura 2 for the board to draw, and the rule hung off `SurgeSpent`.

    Who is inside is asked when the surge is spent rather than kept as a
    list: the aura travels with the creature.
    """
    c.aura(2, until=When.ENCOUNTER)

    def sicken(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and c.distance(ev.actor) <= 2:
            c.weakened(until=When.EOTNT, on=ev.actor)

    c.watch(SurgeSpent, sicken, until=When.ENCOUNTER, on=c.me, label="m2824a0")


@power(
    "m2824a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2824a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m2824a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2824a2(c: Cast) -> None:
    """Anyone who lands a critical on it is paid for it, for the fight."""
    me = c.me

    def reward(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(5, on=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER, label="m2824a2 crit")


@power(
    "m2824a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2824a3(c: Cast) -> None:
    """Happier shooting into a crowd its own side is standing in.

    `PowerUsed` is emitted with the whole target list before the first
    attack of that power rolls, so the watch decides once whether this use
    qualifies and the gate on the modifier only asks which power is
    rolling. Any other power use clears the latch, so a reaction fired
    mid-burst cannot inherit the bonus.
    """
    me = c.me
    aided = {"power": ""}

    def aimed(ev: PowerUsed) -> None:
        if ev.actor != me:
            return
        friends = set(c.allies())
        wide = _reach_of(ev.power) in _SPREADS
        aided["power"] = ev.power if wide and friends & set(ev.targets) else ""

    c.watch(PowerUsed, aimed, until=When.ENCOUNTER, on=me, label="m2824a3")
    c.bonus(
        "attack",
        2,
        until=When.ENCOUNTER,
        on=me,
        when=lambda ctx: bool(aided["power"]) and ctx.get("power") == aided["power"],
    )


@power(
    "m2824a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2824a4(c: Cast) -> None:
    """Two words, because the printed line names two sorts of going and
    difficult terrain carries a label -- rough ground of any other kind
    still slows it. The first word is the creature's own, which is written
    as its id: the map labels those squares the same way."""
    c.ignores_difficult("m2824", on=c.me)
    c.ignores_difficult("shallow water", on=c.me)


@power(
    "m2824a5",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m2824a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2824a6",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD, Keyword.LIGHTNING],
    damage=Damage("2d6", 5, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
    attack=Attack(vs=REF, printed=6),
)
def m2824a6(c: Cast) -> None:
    """Cold *and* lightning: the header keeps the first of the two printed
    types and both keywords carry the rest. Only the hit dazes; the miss is
    the half damage and nothing else."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m2824a7",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.THUNDER, Keyword.AREA],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m2824a7(c: Cast) -> None:
    """Creatures in the burst, not enemies: it catches its own side as
    readily as anybody's -- which is the point, given m2824a3."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m304
# --------------------------------------------------------------------------


@power(
    "m304a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m304a0(c: Cast) -> None:
    """Hard to catch out with a trap. A trait, armed once."""
    wary_of_traps(c)


@power(
    "m304a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m304a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m304a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.RANGED],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.ACID),
)
def m304a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m304a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m304a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m304a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m304a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m304a5",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label="Allies in the burst"),
)
def m304a5(c: Cast) -> None:
    """The shift is the ally's own free action, so it is offered rather
    than done to it -- `c.may` is how a creature declines.

    `EACH_ALLY` would catch the m304 itself, and the printed target is its
    allies; `other_ally` is the pool that leaves the caster out.
    """
    c.temp_hp(5)
    if c.target is not None and c.may("shift 1 square", who=c.target):
        c.shift(1, who=c.target)


# --------------------------------------------------------------------------
# m432
# --------------------------------------------------------------------------


@power(
    "m432a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m432a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m432a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.RANGED],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.ACID),
)
def m432a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4789
# --------------------------------------------------------------------------


@power(
    "m4789a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4789a0(c: Cast) -> None:
    """Hard to shoot, no harder to reach. A gate on each defence rather
    than an effect put on and taken off: the range of the attack is only
    known when the defence is read."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(
            d,
            2,
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: _reach_of(ctx.get("power", "")) in _FROM_AFAR,
        )


@power(
    "m4789a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4789a1(c: Cast) -> None:
    """Shooting from hiding and missing does not give it away.

    Attacking clears hidden for whoever swung, so this is written as the
    exemption it is printed as: the miss is noted while the creature is
    still unseen, and the break is undone as it happens.
    """
    me = c.me
    spared: set[int] = set()

    def missed(ev: Miss) -> None:
        if ev.attacker != me or _reach_of(ev.power) != "ranged":
            return
        if c.is_hidden(from_=ev.target):
            spared.add(ev.target)

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in spared:
            spared.discard(ev.target)
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label="m4789a1")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label="m4789a1 keep")


@power(
    "m4789a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m4789a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4789a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 4),
)
def m4789a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4789a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=8),
)
def m4789a4(c: Cast) -> None:
    """No damage on the hit at all: the whole line is the hold and the
    bleed. "Save ends both" is one effect carrying both, not two saved
    against separately."""
    if c.strike():
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )
