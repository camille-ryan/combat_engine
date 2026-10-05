"""Monster abilities, level 6, soldiers.

Thirty-seven stat blocks, 105 rows. Ten of the thirty-seven print no ability
at all and have nothing to decorate: m114, m321, m3084, m397, m4710, m474,
m4779, m4902, m4988, m719. Unlike the other roles at this level there is no
earlier `soldiers.py` sweep to split from -- this is the first pass over the
role at this level.

Conventions, inherited from the level 1-5 soldier sweeps:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as the card prints it, and the damage line goes in the header as
  data;
* a **trait** costs no action, has no target, and arms whatever holds it for
  the rest of the fight, whatever the compendium's action column claims;
* `c.mark`, never `c.condition(Condition.MARKED, ...)` -- only the first sets
  `Relation.MARKED_BY`, and `resolve.attack` already reads that relation to
  apply the standard -2 for an attack that does not include the marker, so a
  plain "marked" clause needs no extra penalty written here;
* a printed Requirement naming the creature's own kit (a greataxe, a bastard
  sword, a shield) is not a gate -- `Gear` is empty on every monster, so
  asking would refuse a working row in every fight (#366);
* "save ends both/all" ties pieces together under one effect wherever
  `c.condition` can say it directly; where it cannot (a mark plus a burn, a
  condition plus a flat stat penalty) the pieces are tied by hand with
  `Effects.apply`'s own `conditions=`/`mods=`/`ongoing=`, so one throw ends
  all of them;
* a card with no range or reach at all is melee 1.

One ref (`m2065`) appears inside a printed Requirement/Effect on `m3308a2`
naming something that is neither a weapon nor a zone this creature owns on
this board; read as flavour left over from a reprint and dropped, the same
way the campaign has already read two such refs on `m1741a2`/`m3284a2`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_02.lurkers_sa import _twice
from combat_engine.content.monsters.level_02.soldiers_sa import _armed, _recharge_when_bloodied
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import _is_bloodied
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    Size,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    Miss,
    MoveStart,
    OpportunityWindow,
    RelationCleared,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, is_, team
from combat_engine.engine.triggers import Trigger, about_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _marked_looks_away(
    world: World, me: int, ev: Any, *, adjacent: bool = False, move_kinds: Any = None
) -> bool:
    """"An [adjacent] enemy marked by it [shifts/moves] or makes an attack
    that does not include it" -- one predicate parameterised by the two
    things the printed cards actually disagree about: whether the enemy has
    to be adjacent, and which movement kinds count. `move_kinds=None` means
    the card has no movement clause at all; `move_kinds="any"` means every
    kind counts; a set names the kinds that do.
    """
    actor = getattr(ev, "actor", None) or getattr(ev, "attacker", None)
    if actor is None or not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    if adjacent and distance_between(world, me, actor) > 1:
        return False
    if isinstance(ev, AttackDeclared):
        return ev.target != me
    if move_kinds is None:
        return False
    if move_kinds == "any":
        return True
    return getattr(ev, "kind_", "") in move_kinds


def _resist_triggering_element(c: Cast, amount: int) -> None:
    """"Gains resist N to the triggering damage type" -- the type is read off
    the `DamageApplied` the trigger carries, not re-derived."""
    ev = c.trigger
    dtype = next((t for t in ev.types() if t in _ELEMENTS), None) if ev is not None else None
    if dtype is not None:
        c.resist(amount, dtype, on=c.me, until=When.ENCOUNTER)


def _took_an_element(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and bool(set(ev.types()) & set(_ELEMENTS))


def _mobbed_bonus(c: Cast, amount: int, *, melee_only: bool = False) -> None:
    """"+N damage against an enemy that has two or more of its allies
    adjacent to it." Counted off the context's own target, since who is
    beside whom changes every time anybody moves."""

    def mobbed(ctx: dict[str, Any]) -> bool:
        if melee_only and ctx.get("ranged"):
            return False
        victim = ctx.get("target")
        if not isinstance(victim, int):
            return False
        return len([a for a in c.within(1, of=victim, side="ally") if a != c.me]) >= 2

    c.bonus("damage", amount, on=c.me, until=When.ENCOUNTER, when=mobbed)


def _punish_marked_looking_away(
    c: Cast, amount: int, *, dtype: DamageType = DamageType.UNTYPED
) -> None:
    """"A marked target that attacks without including it takes N damage" --
    armed once off any at-will row that marks, not re-armed on a second use."""
    me, ref = c.me, c.ref
    label = f"{ref} punish"
    if _armed(c, label):
        return

    def looked_away(ev: AttackDeclared) -> None:
        attacker = ev.attacker
        if attacker is None or attacker == me or ev.target == me:
            return
        if c.world.relations.holds(Relation.MARKED_BY, me, attacker):
            c.flat(amount, dtype=dtype, on=attacker)

    c.watch(AttackDeclared, looked_away, until=When.ENCOUNTER, on=me, label=label)


def _resist_forced_grab_burn(c: Cast, victim: int, amount: int, dtype: DamageType) -> None:
    """"Ongoing N damage until the grab ends" -- tied to the grab's own
    `RelationCleared` rather than to a save, because the card's clock is the
    hold itself and not a throw."""
    held = c.ongoing(amount, dtype, on=victim, until=When.ENCOUNTER)
    if held is None:
        return
    me = c.me

    def released(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.world.effects.end(held, "grab ended")

    c.watch(
        RelationCleared, released, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} {victim} release",
    )


def _burn_while_grabbing_me(c: Cast, amount: int, dtype: DamageType) -> None:
    """"Any creature that grabs it takes ongoing N damage until the grab
    ends" -- the reverse direction of `_resist_forced_grab_burn`: here it is
    the grabber, not the grabbed, who pays."""
    me, ref = c.me, c.ref
    held_fx: dict[int, Effect] = {}

    def grabbed(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != me:
            return
        eff = c.ongoing(amount, dtype, on=ev.source, until=When.ENCOUNTER)
        if eff is not None:
            held_fx[ev.source] = eff

    def released(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != me:
            return
        eff = held_fx.pop(ev.source, None)
        if eff is not None:
            c.world.effects.end(eff, "grab ended")

    c.watch(RelationSet, grabbed, until=When.ENCOUNTER, on=me, label=f"{ref} grabbed-by")
    c.watch(RelationCleared, released, until=When.ENCOUNTER, on=me, label=f"{ref} released-by")


# ==========================================================================
# m1109
# ==========================================================================


@power(
    "m1109a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d12", 2),
)
def m1109a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1109a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 2, kind=LIMITED),
)
def m1109a1(c: Cast) -> None:
    """The printed Requirement naming its own greataxe is not a gate (#366)."""
    if c.strike():
        c.hit()
        c.prone()


@power("m1109a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1109a2(c: Cast) -> None:
    """"+2 instead of +1" when charging -- one extra point on top of the
    charge bonus the engine already grants on its own."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("charge")))
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )


# ==========================================================================
# m1132
# ==========================================================================


@power(
    "m1132a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m1132a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1132a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m1132a1(c: Cast) -> None:
    """The printed Requirement naming its own bastard sword is not a gate
    (#366)."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1132a2",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="a marked target shifts, moves, or makes an attack that does not include it",
    on=(
        Trigger(
            MoveStart,
            lambda w, m, ev: _marked_looks_away(w, m, ev, move_kinds="any"),
            "it moves",
        ),
        Trigger(
            AttackDeclared, lambda w, m, ev: _marked_looks_away(w, m, ev), "it attacks away"
        ),
    ),
)
def m1132a2(c: Cast) -> None:
    actor = getattr(c.trigger, "actor", None) or getattr(c.trigger, "attacker", None)
    if actor is not None:
        c.basic(on=actor)


@power(
    "m1132a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5, kind=LIMITED, half_on_miss=True),
)
def m1132a3(c: Cast) -> None:
    """The printed Requirement naming its own bastard sword is not a gate
    (#366)."""
    if c.strike():
        c.hit()
        c.ongoing(5)
    else:
        c.hit(half=True)
    _recharge_when_bloodied(c)


# ==========================================================================
# m1156
# ==========================================================================


@power(
    "m1156a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m1156a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1156a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 3),
)
def m1156a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1156a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m1156a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m1156a0", on=victim)
    if c.landed:
        if _secondary(c, 9, FORT, victim):
            c.damage("1d8", 0, on=victim)
        c.shift(1)


# ==========================================================================
# m115769
# ==========================================================================


@power(
    "m115769a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115769a0(c: Cast) -> None:
    _mobbed_bonus(c, 5)


@power(
    "m115769a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m115769a1(c: Cast) -> None:
    plus = 2 if c.bloodied() else 0
    if c.strike():
        c.hit()
        c.flat(plus)
        c.mark(until=When.EONT)


@power(
    "m115769a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d10", 9, dtype=DamageType.PSYCHIC),
)
def m115769a2(c: Cast) -> None:
    """"Each creature marked by it in the burst" is narrower than the
    burst's own enemy pool, so a creature it has not marked is simply never
    rolled against."""
    c.shift(3)
    victim = c.target
    if victim is None or not c.marked(on=victim, by=c.me):
        return
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m115769a3",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m115769a3(c: Cast) -> None:
    c.flat(5)
    c.mark(until=When.EONT)


# ==========================================================================
# m1530
# ==========================================================================


@power("m1530a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1530a0(c: Cast) -> None:
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: any(c.is_kind("dragon", on=w) for w in c.within(5)),
    )


@power(
    "m1530a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m1530a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1530a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m1530a2(c: Cast) -> None:
    """"Immobilized and takes a -2 penalty to all defenses (save ends
    both)" -- one effect carrying the condition and the four penalties, so
    one throw ends all of it."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        mods = [(victim, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in ALL_DEFENCES]
        c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS, label=f"{c.ref} hold",
            conditions=[Condition.IMMOBILIZED], mods=mods,
        )


@power("m1530a3", level=6, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m1530a3(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m1685
# ==========================================================================


@power(
    "m1685a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m1685a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1685a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 2, kind=LIMITED),
)
def m1685a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1685a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m1685a2(c: Cast) -> None:
    """"Marked, immobilized, and takes ongoing 5 damage (save ends all)" --
    the immobilize and the burn share one save; the mark is a relation, not
    a `Condition`, so it is ended alongside the hold by hand rather than
    folded into it. "Cannot make trident attacks while the target remains
    immobilized" bans this very row on itself until that hold breaks."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        held = c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS, label=f"{c.ref} hold",
            conditions=[Condition.IMMOBILIZED], ongoing=(5, DamageType.UNTYPED),
        )
        tag = c.mark(on=victim, until=When.ENCOUNTER)
        ban = c.forbid(c.ref, on=c.me, until=When.ENCOUNTER)
        if held is not None:
            if tag is not None:
                held.on_end.append(lambda: c.world.effects.end(tag, "saved"))
            if ban is not None:
                held.on_end.append(lambda: c.world.effects.end(ban, "target freed"))


# ==========================================================================
# m1755
# ==========================================================================


@power(
    "m1755a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5),
)
def m1755a0(c: Cast) -> None:
    """Crit replaces the damage rather than adding to it (4d4+13), so it is
    paid flat past the engine's own max-dice rule. The punish rider is armed
    once off this row and reads the mark relation live from then on."""
    if c.strike():
        _crit_line(c, "4d4", 13)
        c.mark(until=When.EONT)
    _punish_marked_looking_away(c, 2)


@power(
    "m1755a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m1755a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1755a2",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(1),
    target=EACH_ENEMY,
)
def m1755a2(c: Cast) -> None:
    c.flat(2)


# ==========================================================================
# m1808
# ==========================================================================


@power(
    "m1808a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 2),
)
def m1808a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1808a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 2),
)
def m1808a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.shift(2)


# ==========================================================================
# m1813
# ==========================================================================


@power(
    "m1813a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 7),
)
def m1813a0(c: Cast) -> None:
    bonus = 9 if c.bloodied() else 7
    if c.strike():
        if c.crit:
            c.flat(c.roll("1d12") + bonus + 12)
        else:
            c.damage("1d12", bonus)
        c.mark(until=When.EONT)


@power(
    "m1813a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d12", 7, kind=LIMITED),
)
def m1813a1(c: Cast) -> None:
    """The printed Requirement naming its own greatsword is not a gate
    (#366)."""
    bonus = 9 if c.bloodied() else 7
    if c.strike():
        if c.crit:
            c.flat(c.roll("1d12") + bonus + 12)
        else:
            c.damage("1d12", bonus)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


@power("m1813a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1813a2(c: Cast) -> None:
    _mobbed_bonus(c, 5, melee_only=True)


# ==========================================================================
# m1950
# ==========================================================================


@power(
    "m1950a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m1950a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m1950a1",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 4),
    dropped=("Target.condition",),
)
def m1950a1(c: Cast) -> None:
    foe = _restricted_to(c, 1, lambda f: c.is_(Condition.IMMOBILIZED, on=f))
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.DAZED, on=foe, until=When.SAVE_ENDS)


# ==========================================================================
# m2043
# ==========================================================================


@power(
    "m2043a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m2043a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m2043a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m2043a1(c: Cast) -> None:
    """The printed Requirement naming its own longsword is not a gate
    (#366). The granted ally swing is the printed "one ally within 3
    squares makes a melee basic attack as a free action"."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m2043a0", on=victim)
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= 3), None)
    if mate is not None:
        foe = next((f for f in c.enemies() if c.adjacent_to(f, mate)), None)
        if foe is not None:
            c.basic(who=mate, on=foe)


@power(
    "m2043a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2),
)
def m2043a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.charge_at(foe, who=mate)
    _recharge_when_bloodied(c)


@power(
    "m2043a3",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an ally within 5 squares bloodies an enemy",
    on=Trigger(
        Bloodied,
        lambda w, m, ev: (
            ev.source is not None and team(w, ev.source) is team(w, m)
            and distance_between(w, m, ev.source) <= 5
        ),
        "an ally within 5 squares bloodies an enemy",
    ),
)
def m2043a3(c: Cast) -> None:
    ally = getattr(c.trigger, "source", None)
    if ally is None:
        return
    c.temp_hp(5, on=ally)
    c.shift(1, who=ally)


@power(
    "m2043a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="it reduces an enemy to 0 hit points",
    on=Trigger(
        Dropped, lambda w, m, ev: ev.source == m, "it reduces an enemy to 0 hit points"
    ),
)
def m2043a4(c: Cast) -> None:
    if c.spend_surge(on=c.me):
        c.heal(35, on=c.me)
    for mate in c.within(1, side="ally"):
        if mate != c.me:
            c.temp_hp(10, on=mate)


# ==========================================================================
# m2786
# ==========================================================================


@power(
    "m2786a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m2786a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2786a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5),
    dropped=("Target.bloodied",),
)
def m2786a1(c: Cast) -> None:
    foe = _restricted_to(c, 1, lambda f: c.bloodied(on=f))
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m3308
# ==========================================================================


@power(
    "m3308a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 5),
)
def m3308a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3308a1",
    level=6,
    usage=ENCOUNTER,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 5),
)
def m3308a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        c.push(1, on=victim)
        if victim is not None and c.marked(on=victim, by=c.me):
            c.shift(1)


@power("m3308a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3308a2(c: Cast) -> None:
    """The "within a [ref]" half names something that is not a zone this
    creature owns on this board -- read as flavour and dropped, the same way
    the campaign has already read two such refs elsewhere; see the module
    docstring. The "guarding" half is exact."""

    def near_ward(_ctx: dict[str, Any]) -> bool:
        return any(distance_between(c.world, c.me, w) <= 4 for w in c.guarding())

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER, when=near_ward)
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=near_ward)


@power("m3308a3", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3308a3(c: Cast) -> None:
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# ==========================================================================
# m3539
# ==========================================================================


@power(
    "m3539a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 4),
)
def m3539a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3539a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 5),
)
def m3539a1(c: Cast) -> None:
    """"The m3539 charges and makes this in place of a melee basic attack" --
    registered as its own charge-replacement basic."""
    c.as_basic(c.ref)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3539a2",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 4),
    trigger="an adjacent target marked by it shifts or attacks a target other than it",
    on=(
        Trigger(
            MoveStart,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True, move_kinds={"shift"}),
            "an adjacent marked target shifts",
        ),
        Trigger(
            AttackDeclared,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True),
            "an adjacent marked target attacks away",
        ),
    ),
)
def m3539a2(c: Cast) -> None:
    """The printed Requirement naming its own shield is not a gate (#366)."""
    foe = getattr(c.trigger, "actor", None) or getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


@power(
    "m3539a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3539a3(c: Cast) -> None:
    """The printed defence is garbled past reading in the spec. Kept as
    "the lower of AC and Reflex", the shape every other row at this level
    that prints the same ambiguity resolves to."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m3539a1", on=victim)
    c.basic(on=victim)


@power(
    "m3539a4",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3539a4(c: Cast) -> None:
    foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m4187
# ==========================================================================


@power(
    "m4187a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m4187a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.ACID)


@power(
    "m4187a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 6),
)
def m4187a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4187a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4187a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m4187a1", on=victim)
    c.use_power("m4187a1", on=victim)
    c.use_power("m4187a0", on=victim)


@power(
    "m4187a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m4187a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        square = next(iter(c.area()), None)
        if square is not None:
            c.summon("m4188", at=square)
    _recharge_when_bloodied(c)


# ==========================================================================
# m4195
# ==========================================================================


@power(
    "m4195a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5),
)
def m4195a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d4", 12)


@power(
    "m4195a1",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 3, dtype=DamageType.THUNDER),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4195a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


def _adjacent_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    actor = ev.actor
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return ev.kind_ == "shift" and distance_between(world, me, actor) <= 1


@power(
    "m4195a2",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an adjacent enemy shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts"),
)
def m4195a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.shift(1)
    c.basic(on=foe)


# ==========================================================================
# m5159
# ==========================================================================


def _holding_nobody_gate(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m5159a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
    requires=_holding_nobody_gate,
    requires_text="it must not have a creature grabbed",
)
def m5159a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        c.grab()


@power(
    "m5159a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m5159a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5159a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.GAZE],
    attack=Attack(vs=WILL, printed=9),
)
def m5159a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    _recharge_when_bloodied(c)


def _attacked_by_me_this_turn(c: Cast) -> set[int]:
    out: set[int] = set()
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == c.me and not ev.ghost:
            break
        if isinstance(ev, AttackDeclared) and ev.attacker == c.me:
            out.add(ev.target)
    return out


@power(
    "m5159a3",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it misses with m5159a0",
    on=Trigger(
        Miss, lambda w, m, ev: ev.attacker == m and ev.power == "m5159a0", "it misses with m5159a0"
    ),
)
def m5159a3(c: Cast) -> None:
    if not c.bloodied():
        return
    already = _attacked_by_me_this_turn(c)
    foe = next((f for f in c.enemies() if f not in already), None)
    if foe is not None:
        c.use_power("m5159a0", on=foe)


@power(
    "m5159a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(DamageApplied, _took_an_element, "it takes an elemental damage type"),
)
def m5159a4(c: Cast) -> None:
    _resist_triggering_element(c, 10)


# ==========================================================================
# m5360
# ==========================================================================


@power("m5360a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5360a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power("m5360a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5360a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m5360a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m5360a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.temp_hp(5, on=c.me)


@power(
    "m5360a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m5360a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.marked(on=victim, by=c.me):
            for foe in c.enemies():
                if distance_between(c.world, c.me, foe) <= 1:
                    c.condition(Condition.IMMOBILIZED, on=foe, until=When.SONT)


@power(
    "m5360a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Ranged(10),
    target=UpTo(2),
)
def m5360a4(c: Cast) -> None:
    """"Recharge when the marked enemy or enemies drop to 0 hit points" --
    armed once, re-firing `restore_use` every time a creature it marked
    falls, for the rest of the encounter."""
    for victim in c.targets[:2]:
        c.mark(on=victim, until=When.ENCOUNTER)
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if _armed(c, label):
        return

    def fallen(ev: Dropped) -> None:
        if ev.actor is not None and c.world.relations.holds(Relation.MARKED_BY, me, ev.actor):
            c.restore_use(ref, on=me)

    c.watch(Dropped, fallen, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m5360a5",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
    trigger="an enemy adjacent to it and marked by it moves, shifts, or makes an attack",
    on=(
        Trigger(
            MoveStart,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True, move_kinds="any"),
            "an adjacent marked enemy moves",
        ),
        Trigger(
            AttackDeclared,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True),
            "an adjacent marked enemy attacks away",
        ),
    ),
)
def m5360a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None) or getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.IMMOBILIZED, on=foe, until=When.SONT)
        c.temp_hp(5, on=c.me)


# ==========================================================================
# m5612
# ==========================================================================


@power("m5612a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5612a0(c: Cast) -> None:
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    me = c.me

    def looked_away(ev: AttackDeclared) -> None:
        attacker = ev.attacker
        if attacker is None or attacker == me or team(c.world, attacker) is team(c.world, me):
            return
        if ev.target == me or distance_between(c.world, me, attacker) > 1:
            return
        c.flat(5, on=attacker)

    c.watch(AttackDeclared, looked_away, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5612a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m5612a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5612a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 7, kind=LIMITED),
    dropped=("c.contract(ref)",),
)
def m5612a2(c: Cast) -> None:
    """The blow plays. The disease it seeds on an end-of-encounter failed
    save has no block of its own in this brief to carry it."""
    if c.strike():
        c.hit()


@power(
    "m5612a3",
    level=6,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(DamageApplied, _took_an_element, "it takes an elemental damage type"),
)
def m5612a3(c: Cast) -> None:
    _resist_triggering_element(c, 5)


# ==========================================================================
# m5825
# ==========================================================================


def _current_quarry(c: Cast) -> int | None:
    prefix = f"{c.ref} target:"
    for eff in c.world.effects.of(c.me):
        if eff.label.startswith(prefix):
            try:
                return int(eff.label[len(prefix):])
            except ValueError:
                return None
    return None


@power("m5825a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5825a0(c: Cast) -> None:
    """"At the start of each turn, chooses one creature it can see" -- the
    live designation `_current_quarry` reads back, re-chosen each round."""
    me, ref = c.me, c.ref

    def choose(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for eff in list(c.world.effects.of(me)):
            if eff.label.startswith(f"{ref} target:"):
                c.world.effects.end(eff, "re-designated")
        foe = next((f for f in c.enemies() if c.can_see(f)), None)
        if foe is not None:
            c.effect(f"{ref} target:{foe}", until=When.ENCOUNTER, on=me)

    c.watch(TurnStart, choose, until=When.ENCOUNTER, on=me, label=f"{ref} choose")


@power(
    "m5825a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.drags_grabbed()",),
)
def m5825a1(c: Cast) -> None:
    """Already the named gap `m6621a1` waits on: nothing makes an ordinary
    move bring a grabbed creature along except the `share=True` a specific
    call opts into, and this trait would need every future move of its own
    to opt in."""


@power(
    "m5825a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
)
def m5825a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.target == _current_quarry(c):
            c.flat(5)
        c.prone()


@power(
    "m5825a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 8, kind=LIMITED),
    requires_text="targets a Medium or smaller creature designated as its quarry",
    dropped=("Target.affected_by",),
)
def m5825a3(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    c.move(half, at="fly")
    victim = c.target
    q = _current_quarry(c)
    small_enough = victim is not None and c.size_of(on=victim) in (
        Size.TINY, Size.SMALL, Size.MEDIUM,
    )
    if victim is not None and victim == q and small_enough and c.strike(on=victim):
        c.hit(on=victim)
        c.grab(on=victim)
    c.move(max(0, c.speed_of() - half), at="fly")


@power(
    "m5825a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
)
def m5825a4(c: Cast) -> None:
    def qualifies(who: int) -> bool:
        return c.is_kind("humanoid", on=who) and c.is_(Condition.DYING, on=who)

    victim = c.target
    if victim is None or not qualifies(victim):
        victim = next((w for w in c.within(1, side="any") if qualifies(w)), None)
    if victim is None:
        return
    if c.coup_de_grace(on=victim):
        c.heal(20, on=c.me)


@power(
    "m5825a5",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m5825a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        me = c.me

        def looked_away(ev: AttackDeclared, v: int = victim) -> None:
            if ev.attacker == v and ev.target != me:
                c.flat(5, on=v)

        c.watch(AttackDeclared, looked_away, until=When.EONT, on=me, label=f"{c.ref} {victim}")


@power(
    "m5825a6",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="the creature designated as its quarry attacks without including it",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: ev.attacker == _current_quarry_w(w, m) and ev.target != m,
        "the quarry attacks away",
    ),
)
def m5825a6(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.charge_at(foe)


def _current_quarry_w(world: World, me: int) -> int | None:
    prefix = "m5825a0 target:"
    for eff in world.effects.of(me):
        if eff.label.startswith(prefix):
            try:
                return int(eff.label[len(prefix):])
            except ValueError:
                return None
    return None


# ==========================================================================
# m5857
# ==========================================================================


@power(
    "m5857a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m5857a0(c: Cast) -> None:
    """Nothing in the engine restricts a creature to free actions after a
    charge -- there is no rule here to lift, so this is complete and inert
    in a fight."""


@power("m5857a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5857a1(c: Cast) -> None:
    """The rider's bonus follows whoever is riding now, re-granted each time
    a new one mounts -- see `m4258a1`'s own note on the same shape."""
    me = c.me
    granted: dict[str, int | None] = {"rider": None}

    def watch_mount(_ev: Any = None) -> None:
        rider = c.rider()
        if rider is not None and rider != granted["rider"]:
            granted["rider"] = rider
            c.bonus(
                "damage", 2, on=rider, kind="power", until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("charge")),
            )

    c.watch(RelationSet, watch_mount, until=When.ENCOUNTER, on=me, label=c.ref)
    watch_mount()


@power(
    "m5857a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
    dropped=("Target.only_grabbed",),
)
def m5857a2(c: Cast) -> None:
    held = c.grabbing()
    victim = held[0] if held else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        if c.charge:
            c.damage("1d8", 0, on=victim)
        c.grab(on=victim)


@power(
    "m5857a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("Target.relation",),
)
def m5857a3(c: Cast) -> None:
    held = c.grabbing()
    victim = c.target if c.target in held else (held[0] if held else None)
    if victim is None:
        return
    c.damage("2d10", 0, on=victim)
    c.ongoing(5, on=victim)


# ==========================================================================
# m5953
# ==========================================================================


@power("m5953a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5953a0(c: Cast) -> None:
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    me = c.me
    for mate in c.allies():
        if mate == me:
            continue
        c.bonus(
            "damage", 0, dice="1d6", on=mate, until=When.ENCOUNTER,
            when=lambda ctx, m=mate: (
                bool(ctx.get("advantage")) and distance_between(c.world, me, m) <= 3
            ),
        )


@power("m5953a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5953a1(c: Cast) -> None:
    _burn_while_grabbing_me(c, 5, DamageType.FIRE)


@power(
    "m5953a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m5953a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        if not c.grabbing():
            c.grab(on=victim)
        _resist_forced_grab_burn(c, victim, 5, DamageType.FIRE)


@power(
    "m5953a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 5),
)
def m5953a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)


@power(
    "m5953a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 4, kind=LIMITED, half_on_miss=True),
)
def m5953a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


# ==========================================================================
# m6025
# ==========================================================================


@power("m6025a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6025a0(c: Cast) -> None:
    def alone(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if not isinstance(victim, int):
            return False
        return not any(a != c.me for a in c.within(1, of=victim, side="enemy"))

    c.bonus("attack", 4, on=c.me, until=When.ENCOUNTER, when=alone)


@power(
    "m6025a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d4", 4),
)
def m6025a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
    c.mark(until=When.EONT)


@power(
    "m6025a2",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 4),
    trigger="an adjacent marked creature shifts or uses an attack that does not include it",
    on=(
        Trigger(
            MoveStart,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True, move_kinds={"shift"}),
            "an adjacent marked creature shifts",
        ),
        Trigger(
            AttackDeclared,
            lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True),
            "an adjacent marked creature attacks away",
        ),
    ),
)
def m6025a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None) or getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.IMMOBILIZED, on=foe, until=When.EONT)


# ==========================================================================
# m6348
# ==========================================================================


def _my_unmarked_opportunity(world: World, me: int, ev: OpportunityWindow) -> bool:
    return ev.actor == me and not is_(world, ev.provoker, Condition.MARKED)


@power(
    "m6348a0",
    level=6,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an unmarked enemy willingly leaves a square adjacent to it",
    on=Trigger(OpportunityWindow, _my_unmarked_opportunity, "an unmarked enemy leaves its aura"),
)
def m6348a0(c: Cast) -> None:
    foe = getattr(c.trigger, "provoker", None)
    if foe is not None:
        c.use_power("m6348a1", on=foe)


@power(
    "m6348a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4),
)
def m6348a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6348a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6348a2(c: Cast) -> None:
    _twice(c, "m6348a1")


@power(
    "m6348a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=9),
)
def m6348a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.push(2, on=victim)
        c.shift(max(1, c.speed_of() // 2))
        mate = next(
            (
                a for a in c.allies()
                if a != c.me and victim is not None and c.adjacent_to(a, victim)
            ),
            None,
        )
        if mate is not None and victim is not None:
            c.basic(who=mate, on=victim)
    else:
        c.push(1, on=victim)
        c.shift(1)
    _recharge_when_bloodied(c)


@power(
    "m6348a4",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an unmarked enemy in its aura uses an attack power that doesn't include it",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: (
            ev.attacker is not None and ev.attacker != m
            and team(w, ev.attacker) is not team(w, m)
            and not is_(w, ev.attacker, Condition.MARKED)
            and distance_between(w, m, ev.attacker) <= 1
            and ev.target != m
        ),
        "an unmarked enemy in its aura attacks away",
    ),
)
def m6348a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m6348a1", on=foe)


# ==========================================================================
# m6424
# ==========================================================================


@power("m6424a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6424a0(c: Cast) -> None:
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    me = c.me
    for mate in c.allies():
        c.bonus(
            "damage", 0, dice="1d6", on=mate, until=When.ENCOUNTER,
            when=lambda ctx, m=mate: distance_between(c.world, me, m) <= 3,
        )


@power(
    "m6424a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 10),
)
def m6424a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6424a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 8),
)
def m6424a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6424a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m6424a3(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.SONT)


@power(
    "m6424a4",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 10),
    trigger="an adjacent enemy marked by it makes an attack that doesn't include him",
    on=Trigger(
        AttackDeclared,
        lambda w, m, ev: _marked_looks_away(w, m, ev, adjacent=True),
        "an adjacent marked enemy attacks away",
    ),
)
def m6424a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m950
# ==========================================================================


@power(
    "m950a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m950a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
    _punish_marked_looking_away(c, 5, dtype=DamageType.PSYCHIC)


@power(
    "m950a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m950a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


# ==========================================================================
# m976
# ==========================================================================


@power(
    "m976a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m976a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m976a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d4", 3),
)
def m976a1(c: Cast) -> None:
    """The element is the caster's own choice, made once per use rather than
    guessed."""
    if not c.strike():
        return
    c.hit()
    element = (
        c.choose([DamageType.COLD, DamageType.NECROTIC], f"{c.ref}: which element")
        or DamageType.COLD
    )
    c.flat(c.roll("1d4"), dtype=element)


@power(
    "m976a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.retarget()",),
)
def m976a2(c: Cast) -> None:
    """The grab and its per-sustain burn play. Changing the tentacle's
    target or walking it up to 5 squares as a later standard action has no
    verb: nothing here lets a sustained hold be aimed at somebody new."""
    victim = c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.grab(on=victim)
        held = c.effect(f"{c.ref} tentacle", until=When.SUSTAIN, sustain=MINOR, on=c.me)
        if held is not None:
            c.on_sustain(held, lambda v=victim: c.damage("1d6", 3, dtype=DamageType.NECROTIC, on=v))


@power(
    "m976a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m976a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.NECROTIC))


@power("m976a4", level=6, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m976a4(c: Cast) -> None:
    c.maximise(on=c.me, until=When.EONT, critical=True)
