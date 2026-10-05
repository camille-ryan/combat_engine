"""Monster abilities, level 12: the second wave of the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("3d6", 5)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the eleven levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; a printed "Ranged 5/10" is a
normal range and a long one and the normal one is what `Range` holds; and a
helper written for an earlier level is imported rather than copied.

Seven things this file had to settle.

**Total concealment from *one* creature is a gated penalty, not a state.**
`c.conceal` names who gains the concealment and not who is denied the sight,
and `c.invisible(to=)` is the wrong half -- being unseen is a relation that
an attack clears, and the printed line here survives the attack. So the -5
is laid on the one attacker and asked about its target, which is the
arrangement level 3 settled on for the -2 and `lurkers.py` reuses.

**"Removed from play" is `Condition.REMOVED` on two clocks, not one.** Three
rows here put the creature inside its victim: the victim's hold and the
caster's absence are two effects on two creatures and one printed "save ends
both", so the second is ended from the first's `on_end` rather than given a
duration of its own. The reappearance hangs there too, because the end of
the hold is the only moment that can be seen, however it ended.

**A printed damage line of two types has nowhere to go in the header.**
`Damage` holds one `dtype`, so those rows declare none and roll in the body
with `dtypes=`, and name `Damage(dtypes=)` -- the arrangement
`soldiers_sa.py` settled on at this level.

**"Takes half damage from everything except force" is the attacker's
waiver**, not the defender's resistance: `c.insubstantial` halves every
blow and the exception has to be handed to whoever swings, which is
`c.ignore_resistance(insubstantial=True)` gated on the type. The gate the
resist reader is built from carries `dtype` and `dtypes`, which is exactly
what this asks and is why it can be asked at all.

**A printed target restriction is not a `Target`.** `Target` filters on
side, count and size and never on what a creature is suffering, so eleven
rows here pick their own victim through `_restricted_to` rather than throw
the use away when the chooser aims them elsewhere, and each names the gap it
has: `Target.relation` where the line is about the caster -- "grabbed by it",
"granting it combat advantage", "affected by its own earlier row" --
`Target.condition` where the creature carries one, and `Target.creature_kind`
where the line is a type word.

**"Each round that it sustains the grab" is a sustain, not a save.**
`c.effect(until=When.SUSTAIN, sustain=MINOR)` plus `c.on_sustain` is the
only pair that pays out per sustain; a `When.SAVE_ENDS` hold would hand the
victim a roll the card never offers.

**A trait whose whole content is the one clause the engine cannot say is
`todo=`, not `dropped=`.** m1763a3 is that row: "cannot spend healing
surges" has no verb and there is nothing else in the sentence, so the row is
refused in play rather than offered empty.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_02.skirmishers_sa import _blinding_cloud
from combat_engine.content.monsters.level_03.skirmishers import _vanish_until_it_swings
from combat_engine.content.monsters.level_06.controllers import _living
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.soldiers import (
    _recharge_on,
    _until_that_blow_lands,
)
from combat_engine.content.monsters.level_08.brutes import _aura, _is_bloodied
from combat_engine.content.monsters.level_09.skirmishers import _underground
from combat_engine.content.monsters.level_10.controllers_sa import _sunlit
from combat_engine.content.monsters.level_10.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_10.skirmishers_sa import _regen_unless_radiant
from combat_engine.content.monsters.level_11.lurkers import (
    _WEAPON_RANGES,
    EVERY_DEFENCE,
    _extra_against_the_unready,
)
from combat_engine.content.monsters.level_11.skirmishers import _release_earlier
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    Escaped,
    Healed,
    Health,
    Hit,
    Ident,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    PowerUsed,
    Ranged,
    Relation,
    Size,
    SurgeSpent,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    by_melee,
    power,
    spread,
)
from combat_engine.engine.events import EffectApplied
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    creatures,
    distance_between,
    has_combat_advantage,
    is_,
    unseen_by,
)
from combat_engine.engine.triggers import Trigger, both, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

#: The four elements a printed "cold, fire, lightning, or thunder" offers.
_FOUR_ELEMENTS = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)

#: The five a printed "acid, cold, fire, lightning, or thunder" offers.
_FIVE_ELEMENTS = (DamageType.ACID, *_FOUR_ELEMENTS)

#: What "dazed, dominated, stunned, or unconscious" comes to as a set, for a
#: row that may only be aimed at a creature in one of those states.
_HELPLESS_ENOUGH = (
    Condition.DAZED,
    Condition.DOMINATED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


def _total_concealment_from(c: Cast, watcher: int, until: When) -> None:
    """Total concealment from one named creature, which is -5 to its swings.

    The engine holds no concealment state and does not need to: the whole of
    what total concealment does is take five off whoever is looking, and a
    modifier on that one creature asked about its *target* says exactly
    that. `c.conceal` names who gains the concealment rather than who is
    denied the sight, and `c.invisible(to=)` is the wrong half -- being
    unseen is a relation an attack clears, and the lines this serves survive
    the attack.
    """
    me = c.me
    c.penalty(
        "attack", 5, until=until, on=watcher,
        when=lambda ctx: ctx.get("target") == me,
    )


def _vanish_until_struck(c: Cast, until: When) -> None:
    """Unseen until it attacks **or** until an attack lands on it.

    `_vanish` holds the first ending and the clock; this adds the second,
    and both listeners are torn down with the veil so a second vanishing
    does not inherit the first one's.
    """
    veil = c.invisible(until=until)
    if veil is None:
        return
    me = c.me

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.world.effects.end(veil, "it was hit")

    seen = c.watch(AttackRolled, swung, until=until, on=me, label=c.ref)
    found = c.watch(Hit, struck, until=until, on=me, label=f"{c.ref} hit")
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))
    veil.on_end.append(lambda: c.world.effects.end(found, "no longer unseen"))


def _blind_to_me(c: Cast, who: int) -> bool:
    """Can that creature not see this one?

    Two separate reasons and the printed line covers both: this creature
    being unseen, which is the `HIDDEN_FROM` relation, and the watcher being
    blinded, which is a condition and nothing to do with hiding.
    """
    return unseen_by(c.world, who, c.me) or is_(c.world, who, Condition.BLINDED)


def _unseen(world: World, eid: int) -> bool:
    """A printed Requirement of "it must be invisible"."""
    return bool(world.relations.targets(Relation.HIDDEN_FROM, eid))


def _dark_zone(c: Cast, dice: str, bonus: int, dtype: DamageType) -> int:
    """A zone of darkness that bites whoever opens a turn inside it.

    `c.burns` catches entering the zone as well, which is a wider sentence
    than "starts its turn within", so the toll is a `TurnStart` watch that
    asks the zone who is standing there -- the arrangement `minions.py`
    settled on at this level for the same shape.

    `blocks_sight` is terrain and so blinds the line of sight of both sides;
    the printed exemption for whatever can see in darkness has nothing on
    the board to ask, there being no darkvision component.
    """
    zone = c.zone(c.area(), blocks_sight=True, until=When.EONT, label=c.ref)
    me, ref = c.me, c.ref

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.damage(dice, bonus, dtype=dtype, on=ev.actor, detail=ref)

    c.watch(TurnStart, toll, until=When.EONT, on=me, label=f"{ref} dark")
    return zone


def _force_goes_through(c: Cast, until: When) -> list[Effect | None]:
    """"Half damage from all attacks except those that deal force damage."

    `c.insubstantial` halves every blow, so the exception is the attacker's
    waiver rather than the defender's resistance -- which is what
    `c.ignore_resistance(insubstantial=True)` is, gated on the type of the
    blow. The gate the resist reader is built from carries `dtype` and
    `dtypes`, which is the one question this needs to ask.
    """
    def is_force(ctx: dict[str, Any]) -> bool:
        kinds = ctx.get("dtypes") or ()
        return DamageType.FORCE in kinds or ctx.get("dtype") is DamageType.FORCE

    return [
        c.ignore_resistance(
            insubstantial=True, on=foe, until=until, when=is_force
        )
        for foe in sorted(c.enemies())
    ]


def _step_beside(c: Cast, who: int, *, reach: int = 20) -> bool:
    """Appear in an unoccupied square next to a named creature.

    `c.teleport` chooses its own destination through the decider, which is
    right for "it teleports 5" and useless for "it reappears adjacent to the
    target". The square is picked here, nearest first.
    """
    pos = c.world.get(who, Position)
    if pos is None:
        return False
    for square in sorted(spread({pos.square}, 1)):
        if square == pos.square or c.in_squares([square]):
            continue
        if c.teleport(reach, to=square):
            return True
    return False


def _step_beside_an_enemy(c: Cast, squares: int) -> bool:
    """Teleport, but only to a square that ends the step next to an enemy.

    The printed proviso -- "provided it ends its movement in a space
    adjacent to an enemy" -- is a constraint on the destination and the
    decider does not take one, so the candidates are walked here.
    """
    for square in sorted(spread({c.here}, squares)):
        if square == c.here or c.in_squares([square]):
            continue
        if not c.in_squares(spread({square}, 1), side="enemy"):
            continue
        if c.teleport(squares, to=square):
            return True
    return False


def _marked_by(world: World, me: int, label: str) -> list[int]:
    """Whoever is carrying an effect of mine with that label.

    `c.suffering` is this question from a `Cast`; a declared trigger's
    predicate is handed `(world, me, event)` and no `Cast`, so it is asked
    the same way here.
    """
    found = [
        eid
        for eid in creatures(world)
        if eid != me
        and any(
            eff.source == me and eff.label == label for eff in world.effects.of(eid)
        )
    ]
    return sorted(found)


def _steps_this_turn(c: Cast, who: int) -> Callable[[], int]:
    """How far that creature has moved since its turn opened.

    `Moved` is one step and no component keeps a turn's worth of them, so
    the count is kept here and cleared at the start of each of that
    creature's turns -- the arrangement `minions.py` settled on for the same
    printed shape.
    """
    walked = {"squares": 0}

    def opened(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == who:
            walked["squares"] = 0

    def stepped(ev: Moved) -> None:
        if ev.actor == who:
            walked["squares"] += 1

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} opened")
    c.watch(Moved, stepped, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} walked")
    return lambda: walked["squares"]


def _missed_me(c: Cast, ev: Any) -> bool:
    """Was the blow this damage belongs to a miss?

    `DamageRolled` says nothing about the roll behind it, so the nearest
    earlier `Hit` or `Miss` at this creature is read off the log -- the same
    place `level_08/brutes.py` goes for an attribution no event carries.
    """
    me = c.me
    for past in reversed(c.world.bus.log[: ev.seq]):
        if isinstance(past, Hit) and past.target == me:
            return False
        if isinstance(past, Miss) and past.target == me:
            return True
    return False


# ==========================================================================
# m1114
# ==========================================================================


@power(
    "m1114a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d4", 5),
)
def m1114a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1114a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m1114a1(c: Cast) -> None:
    """Two uses of the row the card names rather than two copies of its line,
    so the numbers stay in one header."""
    for _ in range(2):
        c.use_power("m1114a0", on=c.target)


@power(
    "m1114a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d4", 10, kind=LIMITED),
)
def m1114a2(c: Cast) -> None:
    """The choice is a recolouring of the blow, not a second damage line.

    `c.deals` is the override the printed sentence means -- "have the attack
    deal cold damage *instead*" -- and it is laid for this blow and taken
    straight back off, because the permission is about this attack and not
    about the rest of the turn. Declining it leaves the header's own untyped
    line, which is the "normal damage" branch.
    """
    dtype = c.choose(
        list(_FOUR_ELEMENTS),
        "m1114a2: which element, or normal damage",
        optional=True,
        decline="normal damage",
    )
    recolour = c.deals(dtype, until=When.EOT, on=c.me) if dtype is not None else None
    try:
        if c.strike():
            c.hit()
    finally:
        if recolour is not None:
            c.world.effects.end(recolour, "the blow is dealt")


@power(
    "m1114a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
)
def m1114a3(c: Cast) -> None:
    """No attack roll printed: the vulnerability is the whole of it."""
    dtype = c.choose(list(_FOUR_ELEMENTS), "m1114a3: vulnerable to which element")
    if dtype is not None:
        c.vulnerable(10, dtype, until=When.EONT)


@power(
    "m1114a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1114a4(c: Cast) -> None:
    c.teleport(5)


@power(
    "m1114a5",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1114a5(c: Cast) -> None:
    """`skills.modifier` reads `skill:stealth` off `Mods`, so this is a real
    modifier rather than a narrative one. Untyped: the card prints a bare
    "+5 bonus"."""
    c.bonus("skill:stealth", 5, on=c.me, until=When.EONT)


_M1114_SWUNG_AT = "the m1114 is hit or missed by a melee attack"


@power(
    "m1114a6",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger=_M1114_SWUNG_AT,
    on=(
        Trigger(Hit, when=both(targets_me, by_melee), text=_M1114_SWUNG_AT),
        Trigger(Miss, when=both(targets_me, by_melee), text=_M1114_SWUNG_AT),
    ),
)
def m1114a6(c: Cast) -> None:
    """Hit or missed is two events and one hold, so both are declared.

    The concealment is from the attacker alone, which is a gated modifier on
    that one creature rather than a state. The card's second sentence
    exempts this row from a published hazard that has no component on the
    board at all -- nothing to lay and nothing to wait for, so it is not
    marked.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        _total_concealment_from(c, attacker, When.EONT)


@power(
    "m1114a7",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1114a7(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range kind, so every attack carries it."""
    _extra_against_the_unready(c, "2d6")


# ==========================================================================
# m115733
# ==========================================================================


@power(
    "m115733a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115733a0(c: Cast) -> None:
    """Dealt as its own packet rather than as a damage modifier, which would
    add to whatever else was riding along.

    "A creature that cannot see it" is two separate facts -- this one unseen
    and the watcher blinded -- and the printed line covers both.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _blind_to_me(c, ev.target):
            c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m115733a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m115733a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115733a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=5, kind=MINION),
)
def m115733a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m115733a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m115733a3(c: Cast) -> None:
    """The cloud blinds whoever is standing in it and blocks sight both ways.

    The printed exemption -- everyone *except* this creature -- is the half
    the blind can honour and the sight cannot: `blocks_sight` is terrain.
    """
    _blinding_cloud(c, 1)


# ==========================================================================
# m115912
# ==========================================================================


@power(
    "m115912a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m115912a0(c: Cast) -> None:
    """Sunlight is a property of the fight rather than of any one square,
    which is what `c.terrain` asks, and it is asked at the start of each turn
    rather than once, because a fight can move into the open."""
    _sunlit(c, 10)


@power(
    "m115912a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115912a1(c: Cast) -> None:
    _regen_unless_radiant(c, 10)


@power(
    "m115912a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 5),
)
def m115912a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115912a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d10", 10),
    dropped=("Target.condition",),
)
def m115912a3(c: Cast) -> None:
    """Four states and one printed target line. The row picks a creature in
    one of them rather than being thrown away when the chooser aims it
    elsewhere -- `Target` filters on side, count and size and never on what
    a creature is suffering, so `Target.condition` is the gap."""
    victim = _restricted_to(
        c, 1, lambda f: any(is_(c.world, f, cond) for cond in _HELPLESS_ENOUGH)
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(20, on=c.me)


@power(
    "m115912a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m115912a4(c: Cast) -> None:
    """A shape it cannot fight in, and no printed way out of it.

    `Condition.STUNNED` would be the obvious way to write "cannot attack"
    and is the wrong one -- `actions.legal` offers a creature that cannot
    act nothing but the end of its turn -- so the attacks are taken away and
    handed back when the shape goes. `revert=None` because the card names no
    action to drop it; the clock is the only way out.

    "Can move through enemies' spaces" is `c.phasing`, which is the nearest
    thing the engine holds and is wider: it walks through walls too. The
    printed +5 is a **power** bonus, and the card says so.
    """
    shape = c.form(
        conditions=(Condition.INSUBSTANTIAL,),
        modes={"fly": 8},
        until=When.SONT,
        revert=None,
        label=c.ref,
    )
    c.hover(on=c.me, until=When.SONT)
    held = [
        c.cannot_attack(on=c.me, until=When.SONT),
        c.bonus("skill:stealth", 5, on=c.me, until=When.SONT, kind="power"),
        c.phasing(until=When.SONT, on=c.me),
    ]
    for hold in held:
        if hold is not None:
            shape.on_end.append(
                lambda hold=hold: c.world.effects.end(hold, "it is solid again")
            )


@power(
    "m115912a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=17),
)
def m115912a5(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit.

    The printed recharge -- "when no creature is dominated by this power" --
    is asked at the top of each turn rather than remembered, because the
    hold can end on a save between one turn and the next. Only one creature
    at a time, so an earlier hold of this row's is released first.
    """
    ref = c.ref
    _recharge_on(c, TurnStart, lambda ev: not ev.ghost and not c.suffering(ref))
    if not c.strike():
        return
    _release_earlier(c, ref)
    c.condition(Condition.DOMINATED, until=When.EONT)


_M115912_HURT = "the m115912 takes damage while bloodied"


def _hurt_while_bloodied(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return _is_bloodied(world, me)


@power(
    "m115912a6",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    trigger=_M115912_HURT,
    on=Trigger(DamageApplied, when=_hurt_while_bloodied, text=_M115912_HURT),
)
def m115912a6(c: Cast) -> None:
    """An hour is longer than any fight, so the encounter is the clock, and
    the minor action the card prints is the real way out.

    The other shape is taken away rather than left available, which is what
    "cannot use m115912a4" says, and handed back with the shape.
    """
    shape = c.form(
        conditions=(Condition.INSUBSTANTIAL,),
        modes={"fly": 12},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    held = [
        c.cannot_attack(on=c.me, until=When.ENCOUNTER),
        c.forbid("m115912a4", on=c.me, until=When.ENCOUNTER),
    ]
    for hold in held:
        if hold is not None:
            shape.on_end.append(
                lambda hold=hold: c.world.effects.end(hold, "it is solid again")
            )


# ==========================================================================
# m1763
# ==========================================================================


@power(
    "m1763a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m1763a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1763a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="requires combat advantage",
        grants_ca=True,
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m1763a1(c: Cast) -> None:
    """The Requirement is about a *pair*, which is what the target line says
    now: `grants_ca` filters the pool, so there is nothing for a `requires=`
    handed only a creature to spell and nothing for the body to re-pick.

    The card's second sentence calls this a melee basic attack and the
    header's own line is that attack's line, so the swing is rolled here
    rather than through `c.basic` -- which would reach for m1763a0, a
    different defence and a different die.
    """
    if c.strike():
        c.hit()


@power(
    "m1763a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1763a2(c: Cast) -> None:
    """The zone is laid once for the whole use, which is what `c.first` is
    for; the attack is rolled per target.

    "Cannot be illuminated" has nothing to ask -- there is no light level on
    the board -- so there is nothing to lay and nothing to wait for.
    """
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
        _dark_zone(c, "1d6", 6, DamageType.NECROTIC)
    if c.strike():
        c.hit()


@power(
    "m1763a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.no_surges()",),
)
def m1763a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and the whole of it is
    the one clause the engine cannot say.

    "Cannot spend healing surges" has no verb: `c.no_healing` stops healing
    outright, which is wider than the card prints. There is nothing else in
    the sentence, so this is `todo=` and not `dropped=` -- a row with an
    empty body offered in play would report working.
    """


# ==========================================================================
# m1795
# ==========================================================================


@power(
    "m1795a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.TELEPORTATION],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 3),
)
def m1795a0(c: Cast) -> None:
    """The teleport's proviso is a constraint on the destination and the
    decider does not take one, so the square is chosen here: only one that
    ends the step next to an enemy will do."""
    if not c.strike():
        return
    c.hit()
    c.penalty(WILL, 5, until=When.SAVE_ENDS)
    _step_beside_an_enemy(c, 5)


@power(
    "m1795a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 5),
)
def m1795a1(c: Cast) -> None:
    """The swing is granted to the target against one of *its* allies, so the
    victim is named outright: `c.basic(who=)` names who swings and the
    creature struck still defaults to this row's own target, which on an
    enemy-targeting row is friendly fire wearing a grant's clothes."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mates = [
        foe for foe in sorted(c.enemies())
        if foe != victim and c.adjacent_to(victim, foe)
    ]
    if mates:
        c.grant_attack(victim, on=mates[0])


@power(
    "m1795a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m1795a2(c: Cast) -> None:
    """It climbs inside, and "save ends both" is two effects on two
    creatures.

    One `c.condition` cannot hold a daze on the victim and an absence on the
    caster, so the victim's hold is the save-ends one and the caster's
    removal is ended from its `on_end`. The Aftereffect hangs there too,
    because the end of the hold is the only moment that can be seen,
    whichever way it ended.

    "Unless it moves its speed" is counted off `Moved`, which is one step and
    the only trace a turn's worth of walking leaves.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=c.me)
    if hold is None:
        return
    walked = _steps_this_turn(c, victim)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or hold.ended:
            return
        if walked() < c.speed_of(victim):
            c.damage("2d6", 5, dtype=DamageType.PSYCHIC, on=victim, detail=c.ref)

    def surfaces() -> None:
        if gone is not None and not gone.ended:
            c.world.effects.end(gone, "it is forced out")
        c.flat(10, dtype=DamageType.PSYCHIC, on=victim)
        _step_beside(c, victim)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} toll")
    hold.on_end.append(surfaces)


# ==========================================================================
# m1975
# ==========================================================================

#: The label `c.invisible` lays, which is `f"{ref} unseen"` -- so m1975a1's
#: veil announces itself under this and m1975a4's printed recharge has
#: something to read. A trait is not a power use, so `PowerUsed` never says
#: m1975a1 happened, and a marker effect laid beside the veil would collide
#: with this exact label rather than add anything.
_M1975_UNSEEN = "m1975a1 unseen"


@power(
    "m1975a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
)
def m1975a0(c: Cast) -> None:
    """An aura whose occupants carry the penalty while they are inside, and a
    toll asked of the zone at the start of a turn rather than of a membership
    list that goes stale the moment anybody moves."""
    ring = _aura(
        c,
        2,
        lambda who: who in c.enemies(),
        lambda who: c.penalty(WILL, 2, until=When.ENCOUNTER, on=who),
    )
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


@power(
    "m1975a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1975a1(c: Cast) -> None:
    """Eight squares in one turn and it is gone, counted as it goes rather
    than totted up at the end: the printed line is "becomes invisible", and
    waiting for the end of the turn would hand it a turn's grace.

    The veil announces itself: `c.invisible` labels its effect
    `f"{ref} unseen"`, which is what m1975a4's printed recharge reads --
    this line is a trait and no `PowerUsed` ever says it happened.
    """
    me = c.me
    walked = {"squares": 0, "gone": False}

    def opened(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            walked["squares"] = 0
            walked["gone"] = False

    def stepped(ev: Moved) -> None:
        if ev.actor != me or walked["gone"]:
            return
        walked["squares"] += 1
        if walked["squares"] >= 8:
            walked["gone"] = True
            c.invisible(until=When.SONT, on=me)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{c.ref} opened")
    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m1975a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 4),
)
def m1975a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1975a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m1975a3(c: Cast) -> None:
    """Two uses of the row the card names, and `c.landed` is what answers
    "if both attacks hit" -- `c.use_power` leaves the borrowed row's last
    attack where this one can read it.

    The grab is laid only when its hands are empty, which is the printed
    "only one creature at a time".
    """
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m1975a2", on=victim)
        if c.landed:
            landed += 1
    if landed == 2 and not c.grabbing(of=c.me):
        c.grab(on=victim)


@power(
    "m1975a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 4, kind=LIMITED),
)
def m1975a4(c: Cast) -> None:
    """A secondary attack with its own defence and its own damage, so its
    printed bonus goes through `scaling.trim` by hand the way a printed
    secondary has since level 2.

    "If it ends this movement adjacent to no other enemy aside from the
    grabbed target" is asked after the step and of the board, not of the
    square it meant to reach.
    """
    me = c.me
    _recharge_on(
        c, EffectApplied, lambda ev: ev.target == me and ev.label == _M1975_UNSEEN
    )
    if c.strike():
        c.hit()
    held = next(iter(c.grabbing(of=me)), None)
    c.shift(2, share=True)
    if held is None:
        return
    if any(foe != held and c.adjacent(foe) for foe in c.enemies()):
        return
    bonus = c.world.scaling.trim(15, c.level)
    if c.attack(bonus, WILL, on=held, as_="secondary"):
        c.damage("2d6", 4, dtype=DamageType.NECROTIC, on=held, detail=c.ref)
        c.stunned(until=When.SAVE_ENDS, on=held)


# ==========================================================================
# m1999
# ==========================================================================


@power(
    "m1999a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 9),
)
def m1999a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1999a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="requires combat advantage against the target",
        grants_ca=True,
    ),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 12, kind=LIMITED),
)
def m1999a1(c: Cast) -> None:
    """"Each round that the m1999 sustains the grab" is a sustain and not a
    save: `c.on_sustain` is the only thing that pays out per sustain, and a
    `When.SAVE_ENDS` hold would hand the victim a roll the card never
    offers. The payout is asked of the relation each time, because a grab can
    be broken between one sustain and the next.

    `victim` is still held in a local because the sustain closure outlives the
    body, where `c.target` does not."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    grip = c.effect(f"{c.ref} grip", until=When.SUSTAIN, sustain=MINOR, on=c.me)

    def each_round() -> None:
        if victim not in c.grabbing(of=c.me):
            return
        c.flat(15, on=victim)
        c.weakened(until=When.EONT, on=victim)

    c.on_sustain(grip, each_round)


@power(
    "m1999a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
)
def m1999a2(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit, and which hold it is
    depends on whether this creature already has the target."""
    victim = c.target
    if victim is None or not _living(c, victim):
        return
    if not c.strike(on=victim):
        return
    if victim in c.grabbing(of=c.me):
        c.stunned(until=When.EONT, on=victim)
    else:
        c.dazed(until=When.EONT, on=victim)


@power(
    "m1999a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1999a3(c: Cast) -> None:
    """"Until it attacks" is the one ending and there is no clock, so the
    veil runs to the end of the fight and the roll ends it -- whichever way
    the die falls, which is what attacking means here."""
    _vanish_until_it_swings(c, When.ENCOUNTER)


# ==========================================================================
# m2011
# ==========================================================================

#: The label that says this creature is wearing a body. Both of its printed
#: Requirements -- "requires a possessed body" and "requires its own form" --
#: are the two sides of this one effect.
_M2011_BODY = "m2011a3 body"


def _wearing_a_body(world: World, eid: int) -> bool:
    return any(eff.label == _M2011_BODY for eff in world.effects.of(eid))


def _in_its_own_form(world: World, eid: int) -> bool:
    return not _wearing_a_body(world, eid)


def _vacant_bodies(c: Cast) -> list[int]:
    """A dead or unconscious Medium-or-smaller humanoid within reach.

    `c.enemies` and `c.allies` both filter out the dead, which is exactly the
    half this row wants, so the pool is `query.creatures` -- everything with
    hit points and a square, corpses included -- and the hit points are read
    rather than inferred.
    """
    small_enough = (Size.TINY, Size.SMALL, Size.MEDIUM)
    me = c.me
    found: list[int] = []
    for who in creatures(c.world):
        if who == me:
            continue
        health = c.world.get(who, Health)
        if health is None:
            continue
        if health.hp > 0 and not is_(c.world, who, Condition.UNCONSCIOUS):
            continue
        if not c.is_kind("humanoid", on=who):
            continue
        if c.size_of(on=who) not in small_enough:
            continue
        if adjacent(c.world, me, who):
            found.append(who)
    return sorted(found)


@power(
    "m2011a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 4),
    requires=_wearing_a_body,
    requires_text="the m2011 must be in a possessed body",
)
def m2011a0(c: Cast) -> None:
    """Two packets on one hit line and the header holds one, so the necrotic
    half is rolled in the body -- "plus" is a second blow and not a second
    type of the first."""
    if c.strike():
        c.hit()
        c.damage("1d6", 4, dtype=DamageType.NECROTIC, detail=c.ref)


@power(
    "m2011a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
    requires=_in_its_own_form,
    requires_text="the m2011 must be in its own form",
)
def m2011a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2011a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="requires combat advantage against the target",
        grants_ca=True,
    ),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d12", 8, kind=LIMITED),
    requires=_wearing_a_body,
    requires_text="the m2011 must be in a possessed body",
)
def m2011a2(c: Cast) -> None:
    """Half the Requirement is about the creature and half about a pair, so the
    first is still a gate and the second is now the target line. `requires=`
    keeps only the half that is not the target restriction.

    The sixteen is a printed number rather than a surge: no healing surge is
    named, and a monster spends one only where a row says so.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: adjacent(c.world, me, ev.actor))
    if not c.strike():
        return
    c.hit()
    c.weakened(until=When.SAVE_ENDS)
    c.heal(16, on=me)


@power(
    "m2011a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.inhabit(body)",),
)
def m2011a3(c: Cast) -> None:
    """Wearing a corpse, and the one half of it the board cannot hold.

    What plays: the body is found and claimed, the spirit's own attack and
    its insubstantial quality go, the body's attacks and its Strength arrive,
    the temporary hit points are laid, healing the subject wounds the
    occupant, the subject cannot be healed, and a minor action gets out
    again and bars that body for the rest of the fight.

    What does not: "close and area attacks hit the possessed subject **and**
    the m2011" wants two bodies in one square that one blow reaches, and
    nothing joins two creatures that way -- `c.merge` goes the other way and
    takes the occupant out of reach entirely. `c.inhabit(body)` is the gap.
    """
    me = c.me
    if _wearing_a_body(c.world, me):
        return
    bodies = _vacant_bodies(c)
    if not bodies:
        return
    body = c.choose(bodies, "m2011a3: which body")
    if body is None:
        return
    worn = c.effect(_M2011_BODY, until=When.ENCOUNTER, on=me)
    held = [
        c.forbid("m2011a1", on=me, until=When.ENCOUNTER),
        c.bonus("skill:athletics", 7, on=me, until=When.ENCOUNTER),
        c.no_healing(on=body, until=When.ENCOUNTER),
    ]
    c.cure(Condition.INSUBSTANTIAL, on=me)
    c.temp_hp(33, on=me)

    def wounded(ev: Healed) -> None:
        if ev.target == body and ev.amount > 0:
            c.flat(ev.amount, on=me)

    watcher = c.watch(
        Healed, wounded, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )

    def shed() -> None:
        for hold in [*held, watcher]:
            if hold is not None and not hold.ended:
                c.world.effects.end(hold, "it has left the body")
        c.prone(on=body)
        c.forbid("m2011a3", on=me, until=When.ENCOUNTER)

    if worn is not None:
        worn.on_end.append(shed)
        c.endable(worn, MINOR)


@power(
    "m2011a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2011a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Sunlight is a property
    of the fight, which is what `c.terrain` asks, and it is asked at the
    start of each turn rather than once, because a fight can move into the
    open."""
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        c.dazed(on=me, until=When.EOT)
        c.forbid("m2011a3", on=me, until=When.EOT)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} sun")


# ==========================================================================
# m2336
# ==========================================================================


@power(
    "m2336a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 2),
)
def m2336a0(c: Cast) -> None:
    """A high-crit line and a two-step escalation.

    The printed crit total is the header's own dice maxed -- which `c.damage`
    already does -- plus another 2d8, and that extra die is **rolled**:
    adding it inside the crit branch with `c.damage` would get the maximum
    instead, so it goes through `c.flat(c.roll(...))`.

    Each failed save ends the hold before it, so the victim never carries two
    of these and never gets two saves against one printed sentence. The -2
    is carried again each time, because the card prints it on every step.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.crit:
        c.flat(c.roll("2d8"), on=victim)
    bonus = c.world.scaling.trim(13, c.level)
    if not c.attack(bonus, FORT, on=victim, as_="secondary"):
        return

    def second_failure(eff: Effect) -> None:
        c.world.effects.end(eff, "the second save failed")
        c.condition(
            Condition.STUNNED,
            until=When.SAVE_ENDS,
            save_mod=-2,
            on=victim,
            ongoing=(5, DamageType.POISON),
        )

    def first_failure(eff: Effect) -> None:
        c.world.effects.end(eff, "the first save failed")
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            save_mod=-2,
            on=victim,
            ongoing=(5, DamageType.POISON),
            escalate=second_failure,
        )

    c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        save_mod=-2,
        on=victim,
        ongoing=(5, DamageType.POISON),
        escalate=first_failure,
    )


@power(
    "m2336a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m2336a1(c: Cast) -> None:
    for _ in range(2):
        c.use_power("m2336a0", on=c.target)


_M2336_FELLED = "the m2336 is reduced to 0 hit points"


@power(
    "m2336a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M2336_FELLED,
    on=Trigger(
        Dropped,
        when=lambda world, me, ev: getattr(ev, "actor", None) == me,
        text=_M2336_FELLED,
    ),
)
def m2336a2(c: Cast) -> None:
    """No attack roll printed at all: the blind simply lands."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m2336a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2336a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    _extra_against_the_unready(c, "2d6")


@power(
    "m2336a4",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2336a4(c: Cast) -> None:
    """The guard goes up before the step, because the openings it answers
    happen during it, and it is asked of the attack's own `opportunity` key
    rather than of a kind of row. Untyped: the card prints "+4 bonus"."""
    c.bonus(
        AC, 4, on=c.me, until=When.EOT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(4)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.grants_advantage(on=foe, until=When.EONT)


@power(
    "m2336a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m2336a5(c: Cast) -> None:
    """A plain clock and no second ending: this one is not broken by
    attacking, which is why `_vanish` is the wrong shape for it."""
    c.invisible(until=When.EONT, on=c.me)


# ==========================================================================
# m2342
# ==========================================================================

#: The guise m2342a1 leaves, which is what the other two rows mean by "the
#: target on which it has used m2342a1". Appearance has no combat meaning of
#: its own; being *this* creature's double has, and that is what is held.
_M2342_GUISE = "m2342a1 guise"


def _the_double(c: Cast) -> int | None:
    for who in c.suffering(_M2342_GUISE):
        return who
    return None


@power(
    "m2342a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 6),
    dropped=("c.no_surges()",),
)
def m2342a0(c: Cast) -> None:
    """The blow plays. "Cannot spend healing surges" has no verb --
    `c.no_healing` stops healing outright, which is wider than the card
    prints -- so the narrower sentence is named rather than approximated."""
    if c.strike():
        c.hit()


@power(
    "m2342a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m2342a1(c: Cast) -> None:
    """The shared surge is read in the `Healed` interrupt window, where the
    amount is still negotiable, and gated on a surge having just been spent
    -- `SurgeSpent` arrives first and is the only thing that tells a surge's
    healing from any other.

    The printed recharge is "when nobody is under this effect", so it is
    asked at the top of each turn rather than remembered.
    """
    me, ref = c.me, c.ref
    _recharge_on(
        c, TurnStart, lambda ev: not ev.ghost and not c.suffering(_M2342_GUISE)
    )
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    _release_earlier(c, _M2342_GUISE)
    c.effect(_M2342_GUISE, until=When.ENCOUNTER, on=victim)
    surged = {"on": False}

    def spent(ev: SurgeSpent) -> None:
        if ev.actor == victim:
            surged["on"] = True

    def split(ev: Healed) -> None:
        if ev.target != victim or not surged["on"] or ev.amount <= 0:
            return
        surged["on"] = False
        half = ev.amount // 2
        ev.amount -= half
        if half:
            c.heal(half, on=me)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label=f"{ref} surge")
    c.watch(
        Healed, split, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=ref
    )


_M2342_SWUNG_AT = (
    "the m2342 is subject to a melee or ranged attack while bloodied and "
    "adjacent to the target of m2342a1"
)


def _beside_its_double(world: World, me: int, ev: Any) -> bool:
    """Aimed at me, by a melee or ranged row, while I am bloodied and
    standing next to my double.

    The reach kind is read off the row behind the swing: a close burst is
    neither melee nor ranged, which is the whole reason the pair is written
    out.
    """
    if getattr(ev, "target", None) != me or not _is_bloodied(world, me):
        return False
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    if row is None or row.reach.kind not in _WEAPON_RANGES:
        return False
    return any(
        adjacent(world, me, who) for who in _marked_by(world, me, _M2342_GUISE)
    )


@power(
    "m2342a2",
    level=12,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2342_SWUNG_AT,
    on=Trigger(AttackDeclared, when=_beside_its_double, text=_M2342_SWUNG_AT),
)
def m2342a2(c: Cast) -> None:
    """The declaration is the window a redirection needs: after the die is
    down there is a result that would have to be thrown out and rolled again
    against a different defence."""
    double = _the_double(c)
    if double is not None:
        c.redirect(to=double)


_M2342_HURT = (
    "the m2342 is attacked while within 5 squares of the target of m2342a1"
)


def _hurt_near_its_double(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return any(
        distance_between(world, me, who) <= 5
        for who in _marked_by(world, me, _M2342_GUISE)
    )


@power(
    "m2342a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2342_HURT,
    on=Trigger(
        DamageRolled,
        when=_hurt_near_its_double,
        text=_M2342_HURT,
        window=Window.BEFORE,
    ),
)
def m2342a3(c: Cast) -> None:
    """`DamageRolled` in the interrupt window is where the amount is still
    negotiable and can be read back, which is the only place a printed
    "takes half and the other takes the rest" can be said."""
    ev = c.trigger
    double = _the_double(c)
    if ev is None or double is None:
        return
    amount = max(0, getattr(ev, "amount", 0))
    if amount <= 0:
        return
    half = amount // 2
    ev.amount -= half
    if half:
        c.flat(half, dtype=ev.dtype, on=double)


# ==========================================================================
# m2556
# ==========================================================================


@power(
    "m2556a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m2556a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2556a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2556a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2556a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m2556a2(c: Cast) -> None:
    """Two endings and one hold: its own attack roll, whichever way the die
    falls, and a blow landing on it."""
    _vanish_until_struck(c, When.ENCOUNTER)


# ==========================================================================
# m2595
# ==========================================================================


def _coated_secondary(c: Cast) -> None:
    """The printed "Secondary Attack +15 vs Fortitude; see m2595a4".

    The poison is a row of its own because both weapon rows name it, so the
    secondary rolls here and the effect is handed to that row with the
    target named outright -- the path that skips the range check, the poison
    printing no range of its own.
    """
    victim = c.target
    if victim is None:
        return
    bonus = c.world.scaling.trim(15, c.level)
    if c.attack(bonus, FORT, on=victim, as_="secondary"):
        c.use_power("m2595a4", on=victim)


@power(
    "m2595a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m2595a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _coated_secondary(c)


@power(
    "m2595a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.WEAPON],
)
def m2595a1(c: Cast) -> None:
    """Declared with no target: "both attacks cannot target the same
    creature" is a choice made of the pair, and a target list settled before
    the body runs cannot make it. The shift goes between the two swings,
    which is one of the printed orders and the one that puts a second
    creature in reach."""
    reachable = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    first = c.choose(reachable, "m2595a1: the basic attack's target")
    if first is not None:
        c.basic(on=first)
    c.shift(1)
    rest = sorted(
        foe for foe in c.enemies() if foe != first and c.distance(foe) <= 1
    )
    second = c.choose(rest, "m2595a1: the dagger's target")
    if second is not None:
        c.use_power("m2595a0", on=second)


@power(
    "m2595a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 7),
)
def m2595a2(c: Cast) -> None:
    """A printed "Ranged 5/10" is a normal range and a long one, and the
    normal one is what `Range` holds."""
    if c.strike():
        c.hit()
        _coated_secondary(c)


@power(
    "m2595a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2595a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    melee and ranged attacks, so the kinds are given: a close burst is
    neither."""
    _extra_against_the_unready(c, "2d6", _WEAPON_RANGES)


@power(
    "m2595a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
)
def m2595a4(c: Cast) -> None:
    """The coating, as a row, because both weapon rows name it.

    It prints no range of its own -- whatever is dipped in it does -- so the
    melee row's reach stands in for the header and both callers hand it
    their target outright. The Aftereffect hangs on the hold ending rather
    than on `escalate`: escalation runs on a *failed* save and an aftereffect
    is what follows the hold going, whichever way it went.
    """
    victim = c.target
    if victim is None:
        return
    hold = c.blinded(until=When.SAVE_ENDS, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.flat(10, dtype=DamageType.POISON, on=victim)
        )


# ==========================================================================
# m2730
# ==========================================================================

#: The shell m2730a2 raises, read by m2730a1's printed recharge.
_M2730_SHELL = "m2730a2 shell"


@power(
    "m2730a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m2730a0(c: Cast) -> None:
    """Two packets on one hit line and the header holds one, so the cold half
    is rolled in the body: "plus" is a second blow, not a second type of the
    first."""
    if c.strike():
        c.hit()
        c.damage("1d6", 4, dtype=DamageType.COLD, detail=c.ref)


@power(
    "m2730a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    dropped=("c.drag(grabbed)",),
)
def m2730a1(c: Cast) -> None:
    """The flight and the swing play, and so does the grab.

    Declared with no target: the creature it lands beside is chosen after the
    movement, not before the body runs.

    "It can try to move the grabbed target as part of its next move action.
    If it succeeds it can move at full speed, pulling the target with it" has
    nothing to call. `c.shift(share=True)` drags for one shift and this is a
    full move action with a contest in front of it; `c.drag(grabbed)` is the
    gap.
    """
    me = c.me
    _recharge_on(
        c, EffectApplied, lambda ev: ev.target == me and ev.label == _M2730_SHELL
    )
    c.move(8, at="fly")
    prey = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    if not prey:
        return
    victim = c.choose(prey, "m2730a1: who it lands beside")
    if victim is None:
        return
    c.basic(on=victim)
    if c.landed:
        c.grab(on=victim)


@power(
    "m2730a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
)
def m2730a2(c: Cast) -> None:
    """It freezes itself and whatever it is holding into one block.

    The resistance is gated to exclude this row's own cold, which is the
    printed exception, and the gate the resist reader is built from carries
    `power` -- one of the six keys it does carry, which is why this can be
    asked at all.

    The four printed endings are one hold: the save, the minor action, and
    damage getting through all end the same effect, and the grab and the
    conditions come off with it. The Aftereffect hangs on that end, whichever
    way it went.

    "Both can still see their surroundings but cannot use other normal
    senses" has nothing on the board to take away -- there is no sense other
    than sight -- so there is nothing to lay and nothing to wait for.
    """
    me, ref = c.me, c.ref
    held = next(iter(c.grabbing(of=me)), None)
    shell = c.effect(_M2730_SHELL, until=When.ENCOUNTER, on=me)
    if shell is None:
        return

    def not_this_cold(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") != ref

    holds: list[Effect | None] = [
        c.resist(15, on=me, until=When.ENCOUNTER, when=not_this_cold),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
    ]
    if held is not None:
        holds.append(c.resist(15, on=held, until=When.ENCOUNTER, when=not_this_cold))
        burn = c.condition(
            Condition.STUNNED,
            Condition.RESTRAINED,
            until=When.SAVE_ENDS,
            on=held,
            ongoing=(20, DamageType.COLD),
        )
        if burn is not None:
            burn.on_end.append(
                lambda: c.world.effects.end(shell, "the ice is broken")
            )

        def feeds(ev: DamageApplied) -> None:
            if ev.target == held and DamageType.COLD in ev.types():
                c.heal(5, on=me)

        holds.append(
            c.watch(
                DamageApplied, feeds, until=When.ENCOUNTER, on=me,
                label=f"{ref} feeds",
            )
        )

    def cracks(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and not shell.ended:
            c.world.effects.end(shell, "it took a blow in the ice")

    holds.append(
        c.watch(DamageApplied, cracks, until=When.ENCOUNTER, on=me, label=ref)
    )

    def thaws() -> None:
        for hold in holds:
            if hold is not None and not hold.ended:
                c.world.effects.end(hold, "the ice is gone")
        if held is not None:
            c.world.relations.clear(Relation.GRABBED_BY, me, held)
            c.cure(Condition.STUNNED, Condition.RESTRAINED, on=held)
            c.slowed(until=When.EONT, on=held)

    shell.on_end.append(thaws)
    c.endable(shell, MINOR)


# ==========================================================================
# m3275
# ==========================================================================


def _bonded(c: Cast, ref: str, until: When) -> None:
    """"Whenever the m3275 takes damage, the target takes half that much."

    Only one creature at a time, so an earlier bond of this row's is
    released first. Whether the bond is still live is asked each time rather
    than remembered, because it runs on a clock and a blow can land after it.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    _release_earlier(c, ref)
    bond = c.effect(ref, until=until, on=victim)
    if bond is None:
        return

    def shared(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or bond.ended:
            return
        c.flat(ev.amount // 2, on=victim)

    watcher = c.watch(DamageApplied, shared, until=until, on=me, label=ref)
    bond.on_end.append(lambda: c.world.effects.end(watcher, "the bond is gone"))


def _cut_the_bond(c: Cast, ref: str, victim: int) -> None:
    """"The target is no longer affected by m3275a2"."""
    for eff in list(c.world.effects.of(victim)):
        if eff.label == ref and eff.source == c.me:
            c.world.effects.end(eff, f"{ref}: the bond is cut")


@power(
    "m3275a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 8),
)
def m3275a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m3275a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d6", 7),
    requires_text="requires a sickle",
    dropped=("Target.affected_by",),
)
def m3275a1(c: Cast) -> None:
    """"Targets a creature affected by m3275a2" is a restriction `Target`
    cannot express -- a relation to the caster's own earlier row, so
    `Target.relation` -- and the row picks a bonded creature rather than being
    thrown away when the chooser aims it elsewhere."""
    bonded = set(c.suffering("m3275a2"))
    victim = _restricted_to(c, 1, lambda f: f in bonded)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    _cut_the_bond(c, "m3275a2", victim)


@power(
    "m3275a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m3275a2(c: Cast) -> None:
    """No damage line: the bond is the whole of the hit."""
    if c.strike():
        _bonded(c, c.ref, When.EONT)


@power(
    "m3275a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m3275a3(c: Cast) -> None:
    """Three modifiers written separately, so nothing is competing with
    anything: one "+1 bonus to AC and Reflex" written once would be a +1 to
    nothing. Untyped, because the card prints no type word."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3822
# ==========================================================================


def _grabbing_something(world: World, eid: int) -> bool:
    """A printed Requirement of "must be grabbing a creature"."""
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


@power(
    "m3822a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m3822a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3822a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m3822a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3822a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m3822a2(c: Cast) -> None:
    """Two basic attacks, each melee or ranged as the distance decides, and
    each aimed outright: `c.basic` names the attacker in `who` and the
    victim in `on`, and leaving the second off a no-target row means the
    swing simply does not happen."""
    for _ in range(2):
        prey = sorted(c.enemies(), key=lambda foe: (c.distance(foe), foe))
        if not prey:
            return
        victim = prey[0]
        c.basic(on=victim, ranged=c.distance(victim) > 1)


@power(
    "m3822a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
    dropped=("c.escape_penalty()",),
)
def m3822a3(c: Cast) -> None:
    """The blow and the grab play. The -2 does not: a grab is a relation and
    an escape attempt takes a one-off bonus at the moment it is made, so
    there is nowhere to hang a standing modifier on the checks against this
    creature's grabs."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3822a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 5),
)
def m3822a4(c: Cast) -> None:
    """The whole sentence is the target line now. The `requires=` was the same
    restriction asked from the caster's end, so it came out with the body's
    re-pick: an empty pool already makes `_can_land` false. #401."""
    if c.strike():
        c.hit()


_M3822_SLIPPED = "an enemy grabbed by the m3822 escapes"


@power(
    "m3822a5",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 5),
    trigger=_M3822_SLIPPED,
    on=Trigger(
        Escaped,
        when=lambda world, me, ev: (
            getattr(ev, "holder", None) == me and bool(getattr(ev, "success", False))
        ),
        text=_M3822_SLIPPED,
    ),
)
def m3822a5(c: Cast) -> None:
    """"Targets the escaping enemy" is the triggering creature and not this
    row's own target: `Escaped.actor` is the one struggling and `holder` is
    the grabber, which is why the gate reads the second and the swing reads
    the first."""
    victim = getattr(c.trigger, "actor", None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m3822a6",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3822a6(c: Cast) -> None:
    """The Effect line is once for the whole use, which is what `c.first` is
    for, and it is laid whether or not anything was hit."""
    if c.first:
        c.mode("fly", 6, until=When.EONT, on=c.me)
    if c.strike():
        c.hit()


_M3822_BLOW = "an enemy hits or misses the m3822"


def _hurt_while_holding(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return _grabbing_something(world, me)


@power(
    "m3822a7",
    level=12,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    requires=_grabbing_something,
    requires_text="the m3822 must be grabbing a creature",
    trigger=_M3822_BLOW,
    on=Trigger(
        DamageRolled, when=_hurt_while_holding, text=_M3822_BLOW,
        window=Window.BEFORE,
    ),
)
def m3822a7(c: Cast) -> None:
    """The printed trigger is the swing and the printed effect is the damage,
    so the damage is what is answered: `DamageRolled` in the interrupt window
    is the only place the amount is still negotiable.

    Whether the blow was a miss decides how it splits, and `DamageRolled`
    carries nothing about the roll behind it -- so the nearest earlier `Hit`
    or `Miss` at this creature is read off the log.
    """
    ev = c.trigger
    held = next(iter(c.grabbing(of=c.me)), None)
    if ev is None or held is None:
        return
    amount = max(0, getattr(ev, "amount", 0))
    if amount <= 0:
        return
    share = amount if _missed_me(c, ev) else amount // 2
    ev.amount -= share
    if share:
        c.flat(share, dtype=ev.dtype, on=held)


@power(
    "m3822a8",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3822a8(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    _extra_against_the_unready(c, "1d6")


# ==========================================================================
# m3918
# ==========================================================================


@power(
    "m3918a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m3918a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3918a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 3, kind=LIMITED),
    requires=_unseen,
    requires_text="the m3918 must be invisible",
)
def m3918a1(c: Cast) -> None:
    """Being unseen is the `HIDDEN_FROM` relation, which is what the gate
    asks. It is a fact about the creature and not about a pair, so a
    `requires=` is the right place for it."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3918a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3918a2(c: Cast) -> None:
    """A plain clock and no second ending -- this veil is not broken by
    attacking, which is what makes m3918a1 usable at all."""
    c.shift(4)
    c.invisible(until=When.EONT, on=c.me)


@power(
    "m3918a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3918a3(c: Cast) -> None:
    """Ten is a printed number rather than a surge: no healing surge is
    named, and a monster spends one only where a row says so. Four separate
    modifiers, so nothing competes with anything."""
    c.heal(10, on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me)


@power(
    "m3918a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3918a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    _extra_against_the_unready(c, "1d8")


# ==========================================================================
# m4727
# ==========================================================================


@power(
    "m4727a0",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 8),
)
def m4727a0(c: Cast) -> None:
    """Filed as a minor action, which is what the card prints here, where
    m3275's copy of the same line is a standard."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m4727a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d6", 7),
    requires_text="requires a sickle",
    dropped=("Target.affected_by",),
)
def m4727a1(c: Cast) -> None:
    """"Targets a creature affected by m4727a2" is a restriction `Target`
    cannot express -- a relation to the caster's own earlier row, so
    `Target.relation` -- and the row picks a bonded creature."""
    bonded = set(c.suffering("m4727a2"))
    victim = _restricted_to(c, 1, lambda f: f in bonded)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    _cut_the_bond(c, "m4727a2", victim)


@power(
    "m4727a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m4727a2(c: Cast) -> None:
    """No damage line: the bond is the whole of the hit."""
    if c.strike():
        _bonded(c, c.ref, When.EONT)


@power(
    "m4727a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m4727a3(c: Cast) -> None:
    """Three modifiers written separately, untyped, because the card prints
    no type word."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5235
# ==========================================================================


def _not_dominating(world: World, eid: int) -> bool:
    """The printed Requirement: nobody is under this creature's m5235a1."""
    return not _marked_by(world, eid, "m5235a1")


@power(
    "m5235a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    dropped=("Damage(dtypes=)",),
)
def m5235a0(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two
    types, which is what resistance reads as a unit."""
    if not c.strike():
        return
    c.damage(
        "2d8", 11,
        dtypes=(DamageType.FORCE, DamageType.NECROTIC),
        detail=c.ref,
    )
    c.slide(3)


@power(
    "m5235a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    requires=_not_dominating,
    requires_text="the m5235 must not be dominating a creature with this power",
    dropped=("Target.creature_kind",),
)
def m5235a1(c: Cast) -> None:
    """It climbs inside, and the two clocks are one printed sentence.

    The domination is the save-ends hold; the caster's absence is a second
    effect on a second creature, ended from the first's `on_end` -- which is
    also where the reappearance and the free swing hang, because the end of
    the hold is the only moment that can be seen, however it ended.

    The free action the card offers for ending it early is `c.endable` on the
    victim's hold, which is the same door the save opens.
    """
    victim = _restricted_to(
        c, 5, lambda f: _living(c, f) and c.is_kind("humanoid", on=f)
    )
    if victim is None or not c.strike(on=victim):
        return
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=c.me)
    lent = c.grant_row("m5235a0", on=victim, until=When.ENCOUNTER)

    def surfaces() -> None:
        for other in (gone, lent):
            if other is not None and not other.ended:
                c.world.effects.end(other, "the hold is over")
        _step_beside(c, victim)
        c.use_power("m5235a0", on=victim, spend=False)

    hold.on_end.append(surfaces)
    c.endable(hold, FREE)


# ==========================================================================
# m5335
# ==========================================================================


@power(
    "m5335a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5335a0(c: Cast) -> None:
    """Deliberately inert, and complete. The whole printed trait is a Nature
    check nobody rolls on a board: there is no being-mistaken-for state, and
    inventing one would be inventing a roll the engine never makes."""


@power(
    "m5335a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 5),
)
def m5335a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5335a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 5),
    dropped=("Target.condition",),
)
def m5335a2(c: Cast) -> None:
    """"One blinded creature" is a restriction `Target` cannot express -- a
    condition the creature carries, so `Target.condition` -- and the row picks
    a blinded one rather than being thrown away.

    The Sustain line pays out per sustain, which only `c.on_sustain` does,
    and it is asked of the relation each time: a grab can be broken between
    one sustain and the next, and the card sustains *each* of them.
    """
    victim = _restricted_to(c, 1, lambda f: is_(c.world, f, Condition.BLINDED))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    if len(c.grabbing(of=c.me)) < 2:
        c.grab(on=victim)
    grip = c.effect(f"{c.ref} grip", until=When.SUSTAIN, sustain=MINOR, on=c.me)

    def each_sustain() -> None:
        for who in sorted(c.grabbing(of=c.me)):
            c.damage("2d6", 5, on=who, detail=c.ref)

    c.on_sustain(grip, each_sustain)


@power(
    "m5335a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=15),
)
def m5335a3(c: Cast) -> None:
    """No damage line on the hit: the burn and the blind are one hold, so the
    victim never gets two saving throws against one printed sentence."""
    if c.strike():
        c.condition(
            Condition.BLINDED,
            until=When.SAVE_ENDS,
            ongoing=(20, DamageType.POISON),
        )


_M5335_HURT = "an enemy's attack damages the m5335"


def _damaged_by_an_attack(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    return _grabbing_something(world, me)


@power(
    "m5335a4",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    requires=_grabbing_something,
    requires_text="the m5335 must have a creature grabbed",
    trigger=_M5335_HURT,
    on=Trigger(DamageApplied, when=_damaged_by_an_attack, text=_M5335_HURT),
)
def m5335a4(c: Cast) -> None:
    """"Equal to the damage of the triggering attack" is read off the packet
    that landed rather than rolled, so `DamageApplied` is the event: it is
    what actually came off hit points, which is what the card means by the
    damage of the attack."""
    ev = c.trigger
    held = sorted(c.grabbing(of=c.me))
    if ev is None or not held:
        return
    victim = c.choose(held, "m5335a4: which grabbed creature pays")
    if victim is not None:
        c.flat(getattr(ev, "amount", 0), dtype=DamageType.PSYCHIC, on=victim)


# ==========================================================================
# m5480
# ==========================================================================

#: The three stat blocks m5480a0 chooses between when it refills its reach.
#: Written out because the printed line names all three and the choice is
#: what the row is made of.
_M5480_LIMBS = ("m5481", "m5482", "m5483")


def _its_limbs(c: Cast) -> list[int]:
    """Whichever of the three are on the board on this creature's side."""
    found: list[int] = []
    for who in c.within(20, side="team"):
        ident = c.world.get(who, Ident)
        if ident is not None and ident.ref in _M5480_LIMBS:
            found.append(who)
    return sorted(found)


@power(
    "m5480a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
)
def m5480a0(c: Cast) -> None:
    """Four on the board at the top of every turn, and the kind is a choice.

    `c.summon` puts a creature on the board **and** in the initiative order,
    which is what "they roll initiative when they appear" says, so the second
    sentence costs nothing extra. The count is taken off `Ident.ref` rather
    than off a list kept here, because one can be killed between turns.

    "Aboveground even if the m5480 is underground" asks for nothing extra:
    being underground is `Movement.using` holding "burrow", the reading level
    9 settled on, and every ordinary square `c.summon` picks is aboveground
    by that reading already.
    """
    me = c.me

    def refill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for _ in range(4 - len(_its_limbs(c))):
            pick = c.choose(list(_M5480_LIMBS), "m5480a0: which appears")
            if pick is None:
                return
            c.summon(pick)

    c.watch(TurnStart, refill, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5480a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5480a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5480a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d12", 8, kind=LIMITED, half_on_miss=True),
    dropped=("Target.relation_from",),
)
def m5480a2(c: Cast) -> None:
    """"Grabbed by a tentacle" is read off its own side's grabs: the limbs
    are separate creatures, so the hold belongs to one of them and not to
    this one. `half_on_miss` is declared data nothing reads, so the Miss
    branch is written out.

    **Deliberately not moved onto `Target.relation`.** That field is measured
    outward from the *caster* -- `holds(relation, actor, target)` -- and this
    hold belongs to an ally, so `relation=GRABBED_BY` would filter the pool to
    the empty set and refuse the row for the whole fight. The gap is a way to
    name whose relation is being asked about. #401.

    The printed recharge goes on top of the die the database files: being
    underground is `Movement.using` holding "burrow", which is held past the
    end of the move and is the only thing that could mean it.
    """
    me = c.me
    _recharge_on(
        c,
        TurnStart,
        lambda ev: not ev.ghost and ev.actor == me and _underground(c.world, me),
    )
    limbs = set(_its_limbs(c))
    victim = _restricted_to(
        c, 1, lambda f: any(f in c.grabbing(of=limb) for limb in limbs)
    )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


@power(
    "m5480a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5480a3(c: Cast) -> None:
    """The burrow, the waiver and the destination.

    "A space that is completely underground" is `Movement.using` holding
    "burrow" -- held past the end of the move, which is why a creature that
    burrowed is still down there -- so travelling at that mode *is* arriving
    underground, and the printed recharge is the other side of the same
    reading: it comes back when the creature opens a turn not burrowing.
    """
    me = c.me
    _recharge_on(
        c,
        TurnStart,
        lambda ev: not ev.ghost and ev.actor == me and not _underground(c.world, me),
    )
    c.no_provoke(until=When.EOT)
    c.move(c.speed_of(), at="burrow")


_M5480_LIMB_FELLED = "an enemy drops one of the m5480's limbs with a melee attack"


def _limb_felled_in_melee(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or getattr(ev, "source", None) is None:
        return False
    ident = world.get(actor, Ident)
    if ident is None or ident.ref not in _M5480_LIMBS:
        return False
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row is None or row.reach.kind == "melee"


@power(
    "m5480a4",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5480_LIMB_FELLED,
    on=Trigger(Dropped, when=_limb_felled_in_melee, text=_M5480_LIMB_FELLED),
)
def m5480a4(c: Cast) -> None:
    """The limb swings, not this creature, so the attack is granted to it and
    the victim is named outright -- `c.grant_attack` takes the swinger first
    and this row's own target is itself.

    "Instead of grabbing it" is left standing: the grab belongs to the
    limb's own row and nothing suppresses a clause of a row somebody else is
    running. The push is the half this row adds.
    """
    ev = c.trigger
    limb = getattr(ev, "actor", None)
    attacker = getattr(ev, "source", None)
    if limb is None or attacker is None:
        return
    if c.grant_attack(limb, on=attacker, damage_bonus=10):
        c.push(5, on=attacker, by=limb)


# ==========================================================================
# m5761
# ==========================================================================


@power(
    "m5761a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.no_raise()",),
)
def m5761a0(c: Cast) -> None:
    """The petrification plays and runs to the end of the fight.

    `Dropped` is the event, because it says who struck the blow where `Died`
    says only who went; `dead` is the half that means killed rather than
    dying.

    "Cannot be raised from the dead" has no gate: `c.reanimate` puts a corpse
    back on the board and takes no account of anything on it, so there is
    nothing to switch off. The card's own cure -- touching the creature --
    needs no verb it has not got, `c.cure` being exactly that, but no action
    is printed for it and the row has no card of its own to offer one.
    """
    me = c.me

    def felled(ev: Dropped) -> None:
        if ev.dead and ev.source == me:
            c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=ev.actor)

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5761a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
    dropped=("Damage(dtypes=)",),
)
def m5761a1(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header, so it is
    rolled here as one blow of two types.

    "If the target is granting combat advantage" is read off the result of
    the swing rather than asked of the board again: a one-shot grant has
    already been spent by the time the blow lands, which is exactly the case
    the rider exists for.
    """
    if not c.strike():
        return
    c.damage(
        "2d6", 8,
        dtypes=(DamageType.NECROTIC, DamageType.POISON),
        detail=c.ref,
    )
    if c.result is not None and c.result.advantage:
        c.ongoing(10)


@power(
    "m5761a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d8", 12, kind=LIMITED, half_on_miss=True),
    dropped=("c.no_surges()",),
)
def m5761a2(c: Cast) -> None:
    """Gone this turn and swinging on the next, which is two turns and one
    row.

    The absence is a hold on this creature with the start of its next turn as
    the clock; the swing is armed on that same moment and rolled from here,
    which is what keeps the header's numbers the ones that land. Declared
    `SELF`, because the creature it ends up beside is not knowable when the
    targets are chosen.

    "Cannot spend healing surges" has no verb -- `c.no_healing` is wider than
    the card prints -- so the narrower sentence is named.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=me)
    if gone is None:
        return

    def resurfaces(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if not gone.ended:
            c.world.effects.end(gone, "it steps back into the fight")
        c.teleport(10, who=me)
        prey = sorted(foe for foe in c.enemies() if c.adjacent(foe))
        if not prey:
            return
        victim = prey[0]
        if c.strike(on=victim):
            c.hit(on=victim)
        else:
            c.hit(on=victim, half=True)

    c.watch(
        TurnStart, resurfaces, until=When.ENCOUNTER, on=me, label=c.ref, once=True
    )


@power(
    "m5761a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m5761a3(c: Cast) -> None:
    """Insubstantial, half concealed, and force goes straight through.

    The force exception is the attacker's waiver and not this creature's
    resistance: `c.insubstantial` halves every blow, so the only way to let
    one type past is `c.ignore_resistance(insubstantial=True)` on whoever
    swings, gated on the blow's type -- which the resist reader's gate
    carries.

    Both printed endings are early ones, so they are watched rather than
    given a duration, and the attack one is on the roll: swinging and missing
    is still attacking.
    """
    me = c.me
    holds: list[Effect | None] = [
        c.insubstantial(until=When.SONT, on=me),
        c.conceal(until=When.SONT, on=me),
        *_force_goes_through(c, When.SONT),
    ]

    def drop(why: str) -> None:
        for hold in holds:
            if hold is not None and not hold.ended:
                c.world.effects.end(hold, why)

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            drop("it attacked")

    def seared(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            drop("it took radiant damage")

    holds.append(c.watch(AttackRolled, swung, until=When.SONT, on=me, label=c.ref))
    holds.append(
        c.watch(DamageApplied, seared, until=When.SONT, on=me, label=f"{c.ref} sun")
    )


_M5761_STRUCK = "an enemy hits the m5761 with a melee attack"


@power(
    "m5761a4",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5761_STRUCK,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M5761_STRUCK),
)
def m5761a4(c: Cast) -> None:
    """The printed trigger reads "hits" and the printed effect is a bonus to
    the defence that decides whether it hit, so the declaration is what is
    answered: by `Hit` the comparison has already been made.

    "Against the triggering attack" is not a duration either, so each guard
    comes down as that creature's blow lands or misses -- which is the first
    moment there is nothing left for it to do.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    for defended in EVERY_DEFENCE:
        guard = c.bonus(
            defended, 4, on=c.me, until=When.EOT, kind="power",
            when=lambda ctx: ctx.get("attacker") == attacker,
        )
        _until_that_blow_lands(c, attacker, guard)


# ==========================================================================
# m5932
# ==========================================================================


@power(
    "m5932a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5932a0(c: Cast) -> None:
    """Breathing underwater costs nothing in a fight -- nothing here drowns
    -- so what is left is the bonus, and `c.terrain` is asked inside the gate
    rather than once when the trait is armed."""
    aquatic_edge(c)


@power(
    "m5932a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 6),
)
def m5932a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5932a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5932a2(c: Cast) -> None:
    """"Until the end of its next turn or until immediately after it attacks"
    is two endings on one hold, which is exactly what `_vanish` holds.

    The two rows recharge each other, which the database files as a plain 6+
    on both; the printed sentence goes on top and the two only ever agree to
    give a row back sooner.
    """
    me = c.me
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m5932a3"
    )
    _vanish(c, When.EONT)


@power(
    "m5932a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(6),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d12", 15, kind=LIMITED),
    requires=_unseen,
    requires_text="the m5932 must be invisible",
)
def m5932a3(c: Cast) -> None:
    """The escape DC has nowhere to go: a grab is a relation and the engine
    has no contest to put a number in.

    The Sustain line pays out per sustain, which only `c.on_sustain` does,
    and the grab it keeps is asked of the relation each time rather than
    remembered.
    """
    me = c.me
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m5932a2"
    )
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.hit(on=victim)
    c.pull(5, on=victim)
    c.grab(on=victim)
    grip = c.effect(f"{c.ref} grip", until=When.SUSTAIN, sustain=STANDARD, on=me)

    def each_sustain() -> None:
        if victim in c.grabbing(of=me):
            c.damage("3d10", 6, on=victim, detail=c.ref)

    c.on_sustain(grip, each_sustain)


# ==========================================================================
# m6096
# ==========================================================================


@power(
    "m6096a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6096a0(c: Cast) -> None:
    """An aura whose toll is paid on a blow rather than carried, so there is
    nothing to hold on the occupants: the aura decides who is inside and the
    `Hit` decides when."""
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def answered(ev: Hit) -> None:
        if ev.target != me or ev.attacker not in c.enemies():
            return
        if ev.attacker not in c.world.zones.occupants(ring):
            return
        from combat_engine.engine import get

        row = get(getattr(ev, "power", "") or "")
        if row is not None and row.reach.kind != "melee":
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.attacker)

    c.watch(Hit, answered, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6096a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6096a1(c: Cast) -> None:
    """Insubstantial except against force, and gone for a turn after radiant.

    The force exception is the attacker's waiver rather than this creature's
    resistance, which is what `c.ignore_resistance(insubstantial=True)` is.
    The radiant clause is the trait switching itself off and back on, so the
    hold is ended and a fresh one laid at the start of the next turn.
    """
    me = c.me
    state: dict[str, Any] = {"hold": c.insubstantial(until=When.ENCOUNTER, on=me)}
    _force_goes_through(c, When.ENCOUNTER)

    def seared(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.RADIANT not in ev.types():
            return
        hold = state["hold"]
        if hold is not None and not hold.ended:
            c.world.effects.end(hold, "radiant damage made it solid")
        state["hold"] = None

    def returns(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or state["hold"] is not None:
            return
        state["hold"] = c.insubstantial(until=When.ENCOUNTER, on=me)

    c.watch(DamageApplied, seared, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, returns, until=When.ENCOUNTER, on=me, label=f"{c.ref} back")


@power(
    "m6096a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
)
def m6096a2(c: Cast) -> None:
    """The extra die is read off the result of this swing rather than asked
    of the board again: a one-shot grant has already been spent by the time
    the blow lands."""
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.damage("1d8", dtype=DamageType.NECROTIC, detail=c.ref)


@power(
    "m6096a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("4d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("Target.affected_by",),
)
def m6096a3(c: Cast) -> None:
    """The caster's absence is tied to the victim's hold, not given a clock
    of its own, and the Aftereffect hangs on that hold ending -- whichever
    way it ended, which is what an aftereffect means.

    The printed recharge is "when nobody is affected by this power", so it is
    asked at the top of each turn rather than remembered.
    """
    ref = c.ref
    _recharge_on(c, TurnStart, lambda ev: not ev.ghost and not c.suffering(ref))
    victim = _restricted_to(
        c, 1, lambda f: has_combat_advantage(c.world, c.me, f)
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=c.me)

    def surfaces() -> None:
        if gone is not None and not gone.ended:
            c.world.effects.end(gone, "the hold is over")
        _step_beside(c, victim, reach=5)

    hold.on_end.append(surfaces)


@power(
    "m6096a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m6096a4(c: Cast) -> None:
    """No damage line: the push and the opening are the whole of the hit. The
    distance is this creature's own speed, which is what "up to its speed"
    means on a monster's card."""
    if not c.strike():
        return
    c.push(c.speed_of())
    c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m6096a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 6, dtype=DamageType.NECROTIC, kind=LIMITED,
                  half_on_miss=True),
)
def m6096a5(c: Cast) -> None:
    """The zone is laid once for the whole use and the attack rolled per
    target. `half_on_miss` is declared data nothing reads, so the Miss branch
    is written out.

    The zone's own toll carries an immobilisation as well as the burn, so it
    is written here rather than through `_dark_zone`.
    """
    me, ref = c.me, c.ref
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
        zone = c.zone(c.area(), blocks_sight=True, until=When.EONT, label=ref)

        def toll(ev: TurnStart) -> None:
            if ev.ghost or ev.actor not in c.enemies():
                return
            if ev.actor not in c.world.zones.occupants(zone):
                return
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)
            c.immobilized(until=When.SOTNT, on=ev.actor)

        c.watch(TurnStart, toll, until=When.EONT, on=me, label=f"{ref} dark")
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6096a6",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6096a6(c: Cast) -> None:
    """A use of the row the card names rather than a copy of its line, so the
    numbers stay in one header."""
    c.use_power("m6096a2", on=c.target)


_M6096_BURNED = "the m6096 takes acid, cold, fire, lightning, or thunder damage"


def _burned_by_an_element(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    kinds = ev.types() if hasattr(ev, "types") else ()
    return any(kind in _FIVE_ELEMENTS for kind in kinds)


@power(
    "m6096a7",
    level=12,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6096_BURNED,
    on=Trigger(DamageApplied, when=_burned_by_an_element, text=_M6096_BURNED),
)
def m6096a7(c: Cast) -> None:
    """Twice a fight, which is `uses=2` and not a second row.

    "Until it uses this power again" is the previous guard being taken down
    rather than a duration, so the standing one is found by its label and
    ended before the new one is laid. The type is read off the packet that
    landed, which is the only thing that knows which element it was.
    """
    ev = c.trigger
    if ev is None:
        return
    kinds = [kind for kind in ev.types() if kind in _FIVE_ELEMENTS]
    if not kinds:
        return
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.of(me)):
        if eff.label == ref and eff.source == me:
            c.world.effects.end(eff, f"{ref}: it is used again")
    c.resist(20, kinds[0], until=When.ENCOUNTER, on=me)
