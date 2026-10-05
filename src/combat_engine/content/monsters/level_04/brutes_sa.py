"""Monster abilities, level 4, brutes: the second sweep.

`brutes.py` beside this file holds the first sweep of this level; the split is
by *when* the work was done rather than by what the creatures are, and the
conventions are that file's and the level-1 to level-3 sweeps':

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=9)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold it
  for the rest of the fight;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`;
* a printed range of "5/10" or "15/30" takes the short number;
* a parenthetical "(+1 to hit while bloodied)" folded into an attack line by the
  compendium is paid as `c.strike(plus=...)` rather than as a standing bonus:
  five rows on one block print it, and five untyped +1s would stack to +5.

Fifteen helpers are imported rather than copied. Nine printed sentences on
these cards are word for word ones already written for another role or another
level -- the shapechanger's two forms, "crit NdX + n", a death throe, "it makes
two X attacks", "both until escape", the saving throw against being floored,
the step into the square the target left, hiding wherever there is cover, and
"recharges when first bloodied".
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.brutes_sa import _felled_by_a_crit
from combat_engine.content.monsters.level_01.skirmishers_sa import _helpless_in_reach
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.misc_sa import (
    _shrug_off_prone,
    _square_of,
    _step_into_vacated,
)
from combat_engine.content.monsters.level_02.skirmishers import _hides_with_cover
from combat_engine.content.monsters.level_02.skirmishers_sa import (
    _two_swings,
    _until_escape,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _missed_me_in_melee,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes_sa import (
    _both_hit,
    _claws_then_bite,
    _press,
    _while_bloodied,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _ongoing_of,
    _two_basics,
)
from combat_engine.content.monsters.level_04.brutes import (
    _change_shape,
    _crit_line,
    _holding,
    _is_bloodied,
    _kin,
)
from combat_engine.content.monsters.level_04.skirmishers import _has_advantage
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    SELF,
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
    Health,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    Moved,
    TurnEnd,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, moving_as
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_charge,
    by_me,
    by_melee,
    hits_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _in_shapes(prefix: str, *words: str):  # noqa: ANN202
    """`brutes._in_shape` for a Requirement that names **two** of the forms.

    "It must be in human or hybrid form" is printed on five rows across the two
    shapechangers here and the single-word gate cannot say it. Undeclared is
    still permissive, for the reason that one gives: a creature that has not
    changed shape yet is in whatever shape it was found in, which the stat
    block does not say, so no attack is ruled out.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(prefix):
                return any(effect.label.endswith(word) for word in words)
        return True

    return gate


def _denies_shift_in(c: Cast, zone: int) -> None:
    """"Enemies in the aura cannot shift" -- held on the geometry.

    `c.cannot_shift` is per creature and runs on the clock; the printed line
    runs on where the creature is standing, so the hold is laid on entry and
    taken back on the way out, which is the shape `Cast._while_inside` uses for
    cover and for difficult terrain.
    """
    me = c.me
    held: dict[int, Effect] = {}

    def on_enter(ev: Any) -> None:
        if ev.zone != zone or ev.actor in held:
            return
        if ev.actor in c.enemies():
            got = c.cannot_shift(on=ev.actor, until=When.ENCOUNTER)
            if got is not None:
                held[ev.actor] = got

    def on_exit(ev: Any) -> None:
        got = held.pop(ev.actor, None) if ev.zone == zone else None
        if got is not None:
            c.world.effects.end(got, "left the aura")

    c.watch(ZoneEntered, on_enter, until=When.ENCOUNTER, on=me, label=f"{c.ref} grip")
    c.watch(ZoneExited, on_exit, until=When.ENCOUNTER, on=me, label=f"{c.ref} release")
    for foe in c.enemies():
        if distance_between(c.world, me, foe) <= 1:
            got = c.cannot_shift(on=foe, until=When.ENCOUNTER)
            if got is not None:
                held[foe] = got


def _held_by_another(c: Cast, foe: int | None) -> bool:
    """"Grabbed by another creature", which is not "grabbed by me"."""
    if foe is None:
        return False
    return any(who != c.me for who in c.grabbed_by(on=foe))


# --------------------------------------------------------------------------
# m1009
# --------------------------------------------------------------------------


@power(
    "m1009a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 3),
)
def m1009a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1009a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m1009a1(c: Cast) -> None:
    """The acid is paid at the top of the victim's turn for as long as the hold
    lasts, which is not save-ends: `_until_escape` is what measures a lifetime
    nothing in `When` can."""
    if c.strike():
        c.hit()
        victim = c.target
        c.grab()
        c.prone()
        burn = c.ongoing(5, DamageType.ACID, until=When.ENCOUNTER)
        if victim is not None:
            _until_escape(c, victim, burn)


@power(
    "m1009a2",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it charges",
    on=Trigger(AttackDeclared, both(by_me, by_charge), "it charges"),
)
def m1009a2(c: Cast) -> None:
    """The ally runs at whatever this creature is charging, read off the
    triggering attack: a reaction declares no target of its own and
    `PowerUsed.targets` would name nobody."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    mates = _kin(c, 5, "m1009")
    if victim is not None and mates:
        c.charge_at(victim, who=mates[0])


# --------------------------------------------------------------------------
# m1023
# --------------------------------------------------------------------------


@power(
    "m1023a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 4),
)
def m1023a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1023a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="grabbed target only",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 4),
)
def m1023a1(c: Cast) -> None:
    """The move is the creature's own and the pull drags the held target along,
    so both take the creature's speed."""
    if c.strike():
        c.hit()
        c.move(c.speed_of())
        c.pull(c.speed_of())


@power(
    "m1023a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1023a2(c: Cast) -> None:
    """Three of the four clauses the engine already keeps: a grab here is a
    relation nothing has to sustain and no condition ends. What is left to say
    is the escape defence -- `escape.attempt` reads a `grab_defence` modifier,
    which is the one hook for a printed number on top of a defence -- and the
    drag when something else moves the creature."""
    me = c.me
    c.bonus("grab_defence", 5, on=me, until=When.ENCOUNTER)

    def dragged(ev: Moved) -> None:
        if ev.actor != me or getattr(ev, "kind_", "") not in ("push", "pull", "slide"):
            return
        for victim in list(c.world.relations.targets(Relation.GRABBED_BY, me)):
            c.pull(10, on=victim)

    c.watch(Moved, dragged, until=When.ENCOUNTER, on=me, label=f"{c.ref} drag")


# --------------------------------------------------------------------------
# m1034
# --------------------------------------------------------------------------


@power(
    "m1034a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m1034a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1034a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.stat_block()",),
)
def m1034a1(c: Cast) -> None:
    """The card says the creature calls up the help described in the encounter's
    own setup text, which is not in the block and not in the spec: there is no
    ref to hand `c.summon` and no count to summon."""


# --------------------------------------------------------------------------
# m1066
# --------------------------------------------------------------------------


@power(
    "m1066a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 4),
)
def m1066a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m1131
# --------------------------------------------------------------------------


@power(
    "m1131a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m1131a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m1131a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d10", 5, kind=LIMITED),
    dropped=("spec.weapon_ref()",),
)
def m1131a1(c: Cast) -> None:
    """The printed recharge is the bloodied line as well as the die, so both are
    armed. The Requirement names a weapon, and a monster's gear is a word in the
    spec rather than a thing in its hands."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1131a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
)
def m1131a2(c: Cast) -> None:
    """Two riders hung on one named creature: the extra die is a gated damage
    bonus read at the blow rather than a second attack, and the reward is paid
    off `Dropped.source`, which is who put the creature down."""
    victim = c.target
    if victim is None:
        return
    me = c.me
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim and not ctx.get("ranged"),
    )

    def fell(ev: Dropped) -> None:
        if ev.actor == victim and ev.source == me:
            c.heal(16, on=me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} feast")


# --------------------------------------------------------------------------
# m115708
# --------------------------------------------------------------------------


@power(
    "m115708a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=8, kind=MINION),
)
def m115708a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115708a1",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=6, kind=MINION),
)
def m115708a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(2, DamageType.POISON)


# --------------------------------------------------------------------------
# m115790
# --------------------------------------------------------------------------


@power(
    "m115790a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115790a0(c: Cast) -> None:
    """"A creature with no allies adjacent to it" is asked of the board at the
    roll, not stored: both the target and whoever is standing beside it move.
    Untyped, because the block prints a bare "+4 bonus"."""
    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None:
            return False
        return not [
            other
            for other in c.within(1, of=foe, side="enemy")
            if other != foe
        ]

    c.bonus("attack", 4, on=me, until=When.ENCOUNTER, when=alone)


@power(
    "m115790a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 6),
)
def m115790a1(c: Cast) -> None:
    """"Did this attack have combat advantage" is read off the result; asking
    the board again is too late, a one-shot grant having been spent."""
    if c.strike():
        if c.result is not None and c.result.advantage:
            c.damage("3d8", 6)
        else:
            c.hit()


@power(
    "m115790a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m115790a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m115922
# --------------------------------------------------------------------------


@power(
    "m115922a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.kill()",),
)
def m115922a0(c: Cast) -> None:
    """A critical hit ends the creature whatever its hit points, and nothing
    says "reduce to 0". `c.flat` of a large number is a blow, which resistance,
    immunity and temporary hit points all read, and this is not one -- and the
    sibling row below turns on which of the two kinds of fall happened, so
    getting it wrong here would be wrong twice."""


@power(
    "m115922a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d12", 2),
)
def m115922a1(c: Cast) -> None:
    """The bigger bonus wants a prone creature *or* one held by somebody else --
    a creature this one is holding itself does not qualify, which is what
    `_held_by_another` is for."""
    if c.strike():
        foe = c.target
        down = foe is not None and c.is_(Condition.PRONE, on=foe)
        if down or _held_by_another(c, foe):
            c.damage("2d12", 7)
        else:
            c.hit()


@power(
    "m115922a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d12", 2),
)
def m115922a2(c: Cast) -> None:
    """`charges=True` so the engine measures reach after the run rather than
    before it; `c.run_at` rather than `c.charge_at`, because the swing the card
    names is this row's own attack line and handing the ref back to
    `charge_at` would re-enter this body."""
    foe = c.target
    if foe is None:
        return
    c.run_at(foe)
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m115922a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it is reduced to 0 hit points, but not by a critical hit",
)
def m115922a3(c: Cast) -> None:
    """Not a declared trigger: `Dropped` carries who struck and not how, so the
    "but not by a critical hit" half is answered off the log, which is the only
    record of the swing left once the creature is down. `c.reanimate` rather
    than writing to `Health` -- the body has already been lifted off the grid
    by the time this runs."""
    if _felled_by_a_crit(c):
        return
    if c.roll("1d20") >= 15:
        c.reanimate(on=c.me, hp=1)


# --------------------------------------------------------------------------
# m1442
# --------------------------------------------------------------------------


@power(
    "m1442a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 6, dtype=DamageType.FIRE),
)
def m1442a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1442a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1442a1(c: Cast) -> None:
    """Two swings and a third if both landed on one creature, which is the
    helper's shape with the same ref in both slots: the card names one attack
    three times rather than two different ones."""
    _claws_then_bite(c, "m1442a0", "m1442a0")


@power(
    "m1442a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1442a2(c: Cast) -> None:
    """The Effect is taken on the last target rather than the first: the printed
    order puts the step after the blast, and the destination is a square just
    outside the area it has already drawn."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    if c.last:
        area = c.area()
        for sq in sorted(spread(area, 1) - area):
            free = c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
            if free and c.teleport(20, to=sq):
                break


# --------------------------------------------------------------------------
# m1510
# --------------------------------------------------------------------------


@power(
    "m1510a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 4),
)
def m1510a0(c: Cast) -> None:
    _crit_line(c, "1d12", 16)


@power(
    "m1510a1",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    dropped=("etl.monster.attack_defence()",),
)
def m1510a1(c: Cast) -> None:
    """The swing is the whole of what the card does; the attack line above it
    extracted as a bonus against no defence at all, which is a compendium
    defect and not a defence to invent. Both modifiers belong to the handed-over
    blow and are taken back when it is over."""
    near = _press(c)
    if not near:
        return
    boost = c.bonus("attack", 4, on=c.me, until=When.EOT)
    extra = c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT)
    try:
        c.basic(on=near[0])
    finally:
        c.end_effect(boost, why="the swing is over")
        c.end_effect(extra, why="the swing is over")


@power(
    "m1510a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 3),
)
def m1510a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m1527
# --------------------------------------------------------------------------


@power(
    "m1527a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 6),
)
def m1527a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1527a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("etl.monster.attack_defence()",),
)
def m1527a1(c: Cast) -> None:
    """Two swings, which plays. The attack line printed above them came out of
    the compendium with a bonus and no defence, so it cannot be declared and
    the row leans on what the creature is already armed with."""
    _two_basics(c, separate=False)


@power(
    "m1527a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="it is first bloodied",
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m1527a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1527a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    trigger="it is reduced to 0 hit points",
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d10", 2, dtype=DamageType.ACID, kind=LIMITED),
)
def m1527a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 1, until=When.SAVE_ENDS)


@power(
    "m1527a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1527a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3133
# --------------------------------------------------------------------------


@power(
    "m3133a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 4),
)
def m3133a0(c: Cast) -> None:
    """The parenthetical "+8 while bloodied" is the racial bonus the sibling
    trait lays, not a second bonus here. The poison is the weapon's and fires on
    its first hit of the fight, which is held as a named effect because there is
    nothing else on a monster that remembers a weapon has been used; the
    secondary bonus is trimmed, the header holding only the primary line."""
    if c.strike():
        c.hit()
        label = f"{c.ref} poison"
        if not any(e.label == label for e in c.world.effects.of(c.me)):
            c.effect(label, until=When.ENCOUNTER, on=c.me)
            if c.attack(c.world.scaling.trim(6, c.level), FORT):
                c.ongoing(5, DamageType.POISON)


@power(
    "m3133a1",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m3133a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3133a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3133a2(c: Cast) -> None:
    """Racial, because that is the word the card prints in front of "bonus", and
    gated at the roll rather than armed on `Bloodied`: the creature can be
    healed back over the line and a bonus laid once would never come off."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="racial", when=_while_bloodied(c))


@power(
    "m3133a3",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3133a3(c: Cast) -> None:
    """The check is rolled against the chosen creature's passive Insight, which
    is what an opposed check comes to when only one side rolls, and the opening
    it buys is spent on the next attack rather than held."""
    foe = next(iter(_press(c, 5)), None)
    if foe is None:
        return
    if c.check("bluff", c.passive("insight", of=foe)):
        c.grants_advantage(on=foe, to="me", once=True)


@power(
    "m3133a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("spec.weapon_ref()",),
)
def m3133a4(c: Cast) -> None:
    """The opening is read from the blow's own context -- `advantage` is in both
    modifier contexts -- and "melee" from the absence of `ranged`. The weapon
    the Requirement names is a word in the spec and not a thing in the
    creature's hands."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and not ctx.get("ranged"),
    )


# --------------------------------------------------------------------------
# m3213
# --------------------------------------------------------------------------


@power(
    "m3213a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 6),
)
def m3213a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3213a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m3213a1(c: Cast) -> None:
    """The step follows the shove into open ground beside the target rather than
    asking the controller for a square, which on a quiet board walks away."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.push(2)
        where = _square_of(c, victim)
        if where is not None:
            for sq in sorted(spread({where}, 1)):
                free = c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
                if free and c.shift(10, to=sq):
                    break


@power(
    "m3213a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3213a2(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_while_bloodied(c))


@power(
    "m3213a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 5),
)
def m3213a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3438
# --------------------------------------------------------------------------


@power(
    "m3438a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=3),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC),
)
def m3438a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3438a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3438a1(c: Cast) -> None:
    """A running tally paid out by hand rather than held as a gated bonus, and
    the reason is ordering: `Hit` is announced before the body deals the blow,
    so a bonus laid there would land on the very attack that earned it. The
    count standing *before* this hit is what "successive attacks" means."""
    me = c.me
    tally = {"n": 0}

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if tally["n"]:
            c.damage(f"{tally['n']}d6", on=ev.target, detail=c.ref)
        tally["n"] += 1

    def missed(ev: Miss) -> None:
        if ev.attacker == me:
            tally["n"] = 0

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} tally")
    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} reset")


@power(
    "m3438a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires=_helpless_in_reach,
    requires_text="a helpless creature must be in reach",
    dropped=("Target.condition", "c.coup_de_grace(ref=)"),
)
def m3438a2(c: Cast) -> None:
    """The two costs it pays are exact and so is the reward; the finisher is
    not. `c.coup_de_grace` needs the row to declare an attack of its own and
    this one prints none -- the card borrows the creature's bite -- so the
    swing is the ordinary granted one and the automatic critical is the clause
    waiting on a ref-taking form."""
    foe = c.target
    if foe is None or not (
        c.is_(Condition.HELPLESS, on=foe) or c.is_(Condition.UNCONSCIOUS, on=foe)
    ):
        return
    c.cure(Condition.INSUBSTANTIAL, on=c.me)
    c.mode("fly", 0, until=When.EONT, on=c.me)
    c.basic(on=foe)
    if not alive(c.world, foe):
        body = c.world.get(c.me, Health)
        if body is not None:
            c.heal(body.max_hp, on=c.me)


# --------------------------------------------------------------------------
# m4295
# --------------------------------------------------------------------------


@power(
    "m4295a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 6),
)
def m4295a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m4295a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m4295a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


@power(
    "m4295a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4295a2(c: Cast) -> None:
    """Untyped: the block prints a bare "+2 bonus", and no duration at all,
    which on a block this shape reads as the rest of the fight."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4313
# --------------------------------------------------------------------------


def _m1065_fell_near(world: World, me: int, ev: Dropped) -> bool:
    """Another named stat block went down within 10 squares.

    `ev.actor` has been lifted off the grid by the time this is asked, so the
    distance is measured to whoever struck it -- which is where the body was --
    and the row is false when nothing struck it, ongoing damage carrying no
    position at all.
    """
    ident = world.get(ev.actor, Ident)
    if ident is None or ident.ref != "m1065" or ev.source is None:
        return False
    return distance_between(world, me, ev.source) <= 10


@power(
    "m4313a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5),
)
def m4313a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4313a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d10", 5),
    requires=_has_advantage,
    requires_text="it must have combat advantage against a creature in reach",
)
def m4313a1(c: Cast) -> None:
    """The Requirement is about the board rather than about the target line, so
    it is a `requires=` and not a marker."""
    if c.strike():
        c.hit()
        c.penalty(AC, 4, until=When.SAVE_ENDS)


@power(
    "m4313a2",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d10", 0, kind=LIMITED, half_on_miss=True),
)
def m4313a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m4313a3",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a creature of the named block within 10 squares drops",
    on=Trigger(Dropped, _m1065_fell_near, "one of the named block nearby drops"),
)
def m4313a3(c: Cast) -> None:
    near = _press(c)
    if near:
        c.use_power("m4313a0", on=near[0])


# --------------------------------------------------------------------------
# m4496
# --------------------------------------------------------------------------


@power(
    "m4496a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m4496a0(c: Cast) -> None:
    """Every attack line on this block prints "+1 to hit while bloodied" in
    parentheses and the block gives it no row of its own. Paid on the swing
    rather than as a standing bonus: five untyped +1s would stack to +5, and
    one typed kind would be a word the card does not print."""
    if c.strike(plus=1 if _is_bloodied(c.world, c.me) else 0):
        c.hit()


@power(
    "m4496a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m4496a1(c: Cast) -> None:
    if c.strike(plus=1 if _is_bloodied(c.world, c.me) else 0):
        c.hit()


@power(
    "m4496a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m4496a2(c: Cast) -> None:
    """The second enemy takes its 6 whether or not the swing landed on the
    first -- the printed clause hangs on the hit, so it is inside the branch,
    and "another" leaves the creature actually struck out."""
    if c.strike(plus=1 if _is_bloodied(c.world, c.me) else 0):
        c.hit()
        other = next((f for f in _press(c) if f != c.target), None)
        if other is not None:
            c.flat(6, on=other)


@power(
    "m4496a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4496a3(c: Cast) -> None:
    if c.strike(plus=1 if _is_bloodied(c.world, c.me) else 0):
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m4496a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d8", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m4496a4(c: Cast) -> None:
    if c.strike(plus=1 if _is_bloodied(c.world, c.me) else 0):
        c.hit()


# --------------------------------------------------------------------------
# m4622
# --------------------------------------------------------------------------


@power(
    "m4622a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4622a0(c: Cast) -> None:
    hurt = _while_bloodied(c)
    c.penalty(AC, 2, on=c.me, until=When.ENCOUNTER, when=hurt)
    c.penalty("attack", 2, on=c.me, until=When.ENCOUNTER, when=hurt)
    c.bonus("damage", 4, on=c.me, until=When.ENCOUNTER, when=hurt)


@power(
    "m4622a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 6),
)
def m4622a1(c: Cast) -> None:
    if c.strike():
        if _is_bloodied(c.world, c.me):
            c.damage("1d10", 12)
        else:
            c.hit()


@power(
    "m4622a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("c.hit_this_turn()", "query.shield_bonus()"),
)
def m4622a2(c: Cast) -> None:
    """The shove and the step into the vacated square are exact. "One creature
    it hit this turn" is a target line `Target` cannot express and nothing
    records what a creature has already struck; the shield the Requirement
    names is not in a monster's hands."""
    victim = c.target
    if victim is None:
        return
    was = _square_of(c, victim)
    c.push(1, on=victim)
    _step_into_vacated(c, was)


@power(
    "m4622a3",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4622a3(c: Cast) -> None:
    _death_throe(c)


# --------------------------------------------------------------------------
# m4632
# --------------------------------------------------------------------------


@power(
    "m4632a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 5),
)
def m4632a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4632a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 0),
)
def m4632a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4632a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 0, kind=LIMITED),
)
def m4632a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# --------------------------------------------------------------------------
# m5079
# --------------------------------------------------------------------------


@power(
    "m5079a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("events.Stood",),
)
def m5079a0(c: Cast) -> None:
    """Getting up off the floor is announced as a `Note` and nothing else --
    `actions.perform` ends the hold and writes a line in the log -- so there is
    no moment at which this row could reach for `c.provoke`. The two-of-us
    half is askable and the trigger is not, which leaves nothing to arm."""


@power(
    "m5079a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4),
)
def m5079a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5079a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m5079a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m5085
# --------------------------------------------------------------------------


@power(
    "m5085a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=8, kind=MINION),
)
def m5085a0(c: Cast) -> None:
    """"Or 12 with a charge attack" is read off `c.charge`, which is the flag
    `use(..., charge=True)` puts on this very use."""
    if c.strike():
        if c.charge:
            c.flat(12)
        else:
            c.hit()


@power(
    "m5085a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=6, kind=MINION),
)
def m5085a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5085a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5085a2(c: Cast) -> None:
    """"Takes a standard action" is broader than a death throe's swing -- the
    creature chooses -- so it is handed an action rather than a basic attack."""
    c.extra_action(STANDARD, on=c.me)


# --------------------------------------------------------------------------
# m5315
# --------------------------------------------------------------------------


@power(
    "m5315a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d6", 5),
)
def m5315a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5315a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
)
def m5315a1(c: Cast) -> None:
    """The shove has no distance printed, so it is the one square a bare push
    means, and the step is aimed at the square the target left rather than
    asked of the controller."""
    victim = c.target
    if victim is None:
        return
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        was = _square_of(c, victim)
        c.push(1)
        c.prone()
        _step_into_vacated(c, was)


@power(
    "m5315a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5315a2(c: Cast) -> None:
    c.resist(5, until=When.EONT)


@power(
    "m5315a3",
    level=4,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m5315a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m5944
# --------------------------------------------------------------------------


@power(
    "m5944a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 8, dtype=DamageType.FIRE),
)
def m5944a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5944a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m5944a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)
        c.slowed(until=When.EOTNT)


@power(
    "m5944a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
)
def m5944a2(c: Cast) -> None:
    """"Recharge if neither attack hits" cannot be a watch on this row's own
    `Miss` -- the misses belong to the two rows it reaches for -- so the use is
    handed back here, which is the same sentence read from the other end."""
    foe = c.target
    if foe is None:
        return
    c.use_power("m5944a1", on=foe)
    first = c.landed
    second = False
    if c.adjacent(foe):
        c.use_power("m5944a0", on=foe)
        second = c.landed
    if first and second:
        c.prone(on=foe)
    if not (first or second):
        c.restore_use(c.ref, on=c.me)


# --------------------------------------------------------------------------
# m5952
# --------------------------------------------------------------------------

#: The prefix on m5952a4's hold, so the three gated rows can read which of the
#: three shapes is in force.
_M5952_SHAPE = "m5952a4 "
_M5952_SHAPES = ("rat", "human", "hybrid")


@power(
    "m5952a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5952a0(c: Cast) -> None:
    """Regeneration lands; the silver that switches it off does not. Nothing
    marks a weapon as silvered, so the suspension clause has no property to
    read."""
    c.regeneration(5)


@power(
    "m5952a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 8),
    requires=_in_shapes(_M5952_SHAPE, "human", "hybrid"),
    requires_text="it must be in one of two of its forms",
)
def m5952a1(c: Cast) -> None:
    """"Plus 5 poison damage" is a second, typed blow and not part of the
    header's expression: the two are resisted separately."""
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m5952a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
    requires=_in_shapes(_M5952_SHAPE, "rat", "hybrid"),
    requires_text="it must be in one of two of its forms",
    dropped=("c.contract(ref)",),
)
def m5952a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the condition and the burn, which
    is what `ongoing=` on `c.condition` is for; two calls would be two saves.
    The disease the first failed save hands over is a block of its own and
    nothing contracts one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m5952a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    charges=True,
    requires=_in_shapes(_M5952_SHAPE, "hybrid"),
    requires_text="it must be in its third form",
)
def m5952a3(c: Cast) -> None:
    """`charges=True` so the run is measured as a charge's; the run itself is
    taken once, after the shoves, which is the printed order."""
    c.push(2)
    if c.last:
        far = [f for f in c.enemies() if c.distance(f) > 1]
        if far:
            c.charge_at(far[0])


@power(
    "m5952a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5952a4(c: Cast) -> None:
    _change_shape(c, _M5952_SHAPE, _M5952_SHAPES)


# --------------------------------------------------------------------------
# m5995
# --------------------------------------------------------------------------


@power(
    "m5995a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 6),
)
def m5995a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5995a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 6),
)
def m5995a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5995a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d8", 9, kind=LIMITED),
)
def m5995a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m6049
# --------------------------------------------------------------------------


@power(
    "m6049a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4),
)
def m6049a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6049a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4, half_on_miss=True),
)
def m6049a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
    else:
        c.hit(half=True)


@power(
    "m6049a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(ConditionApplied, _save_ends_on_me, "a save-ends effect lands on it"),
)
def m6049a2(c: Cast) -> None:
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m6050
# --------------------------------------------------------------------------

#: The hold m6050a4 lays. Two other rows read it: the aura switches its damage
#: type while it stands, and the blow that is halved is halved only then.
_M6050_FLAME = "m6050a4 flame"


def _in_flame(c: Cast) -> bool:
    return any(e.label == _M6050_FLAME for e in c.world.effects.of(c.me))


@power(
    "m6050a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m6050a0(c: Cast) -> None:
    """"Exits the aura **on its turn**" is neither entry nor the close of a
    turn, so it hangs on `ZoneExited` and asks whose turn it is. The damage type
    is read at the toll rather than fixed, because the form row switches it."""
    me = c.me
    zone = c.aura(1, until=When.ENCOUNTER)

    def left(ev: ZoneExited) -> None:
        if ev.zone != zone or ev.actor == me or c.turn_of() != ev.actor:
            return
        dtype = DamageType.FIRE if _in_flame(c) else DamageType.COLD
        c.flat(5, dtype=dtype, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6050a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4),
)
def m6050a1(c: Cast) -> None:
    """"+10 vs AC if the target is bloodied" is a better roll against the same
    defence, which is `plus=` on the swing rather than a second attack line."""
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()


@power(
    "m6050a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 4, dtype=DamageType.FIRE, half_on_miss=True),
)
def m6050a2(c: Cast) -> None:
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6050a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
)
def m6050a3(c: Cast) -> None:
    """Both ends of the step bite, so who was adjacent is collected before the
    teleport and again after it; a creature standing next to both squares is in
    the set once and takes the damage once."""
    amount = 10 if _is_bloodied(c.world, c.me) else 5
    caught = {who for who in c.within(1) if who != c.me}
    c.teleport(5)
    caught |= {who for who in c.within(1) if who != c.me}
    for who in sorted(caught):
        c.flat(amount, dtype=DamageType.FIRE, on=who)


@power(
    "m6050a4",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.POLYMORPH],
    trigger="it is dazed or stunned by an attack",
    on=Trigger(ConditionApplied, _save_ends_on_me, "a hold lands on it"),
)
def m6050a4(c: Cast) -> None:
    """"Until he is no longer dazed or stunned" is not a `When`, so the hold is
    swept as each turn closes and asks the question itself. The halving is taken
    before the blow lands -- `Window.BEFORE` on `DamageRolled` -- and the
    reprisal after it, off the amount that actually came off hit points."""
    me = c.me
    if _in_flame(c):
        return
    if not (c.is_(Condition.DAZED, on=me) or c.is_(Condition.STUNNED, on=me)):
        return
    form = c.effect(_M6050_FLAME, until=When.ENCOUNTER, on=me)

    def soften(ev: DamageRolled) -> None:
        if getattr(ev, "target", None) == me and _in_flame(c):
            c.halve(ev)

    def reprisal(ev: DamageApplied) -> None:
        if ev.target != me or ev.source == me or not _in_flame(c):
            return
        if ev.amount > 1:
            c.flat(ev.amount // 2, dtype=DamageType.FIRE, on=ev.source)

    def done(ev: TurnEnd) -> None:
        if ev.ghost or form is None:
            return
        if not (c.is_(Condition.DAZED, on=me) or c.is_(Condition.STUNNED, on=me)):
            c.world.effects.end(form, "no longer held")

    c.watch(
        DamageRolled, soften, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=f"{c.ref} half",
    )
    c.watch(DamageApplied, reprisal, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")
    c.watch(TurnEnd, done, until=When.ENCOUNTER, on=me, label=f"{c.ref} ends")


@power(
    "m6050a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="it is hit by an enemy's attack",
    on=Trigger(Hit, hits_me, "an enemy hits it"),
)
def m6050a5(c: Cast) -> None:
    who = _triggering_enemy(c)
    if who is not None:
        c.damage("1d6", 7, dtype=DamageType.FIRE, on=who)


# --------------------------------------------------------------------------
# m6190
# --------------------------------------------------------------------------

_M6190_SHAPE = "m6190a3 "
_M6190_SHAPES = ("beast", "human", "hybrid")


@power(
    "m6190a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 6),
    requires=_in_shapes(_M6190_SHAPE, "human", "hybrid"),
    requires_text="it must be in one of two of its forms",
)
def m6190a0(c: Cast) -> None:
    if c.strike():
        foe = c.target
        if foe is not None and c.is_(Condition.PRONE, on=foe):
            c.damage("3d8", 6)
        else:
            c.hit()


@power(
    "m6190a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires=_in_shapes(_M6190_SHAPE, "human", "hybrid"),
    requires_text="it must be in one of two of its forms",
)
def m6190a1(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m6190a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    requires=_in_shapes(_M6190_SHAPE, "human", "hybrid"),
    requires_text="it must be in one of two of its forms",
)
def m6190a2(c: Cast) -> None:
    if c.strike():
        c.prone()


@power(
    "m6190a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6190a3(c: Cast) -> None:
    _change_shape(c, _M6190_SHAPE, _M6190_SHAPES)


@power(
    "m6190a4",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    requires=_in_shapes(_M6190_SHAPE, "beast", "hybrid"),
    requires_text="it must be in one of two of its forms",
)
def m6190a4(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# --------------------------------------------------------------------------
# m6341
# --------------------------------------------------------------------------


@power(
    "m6341a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6341a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m6341a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=7, kind=MINION),
)
def m6341a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6341a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.ZONE],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    attack=Attack(vs=FORT, printed=7),
    damage=Damage(bonus=5, dtype=DamageType.POISON, kind=MINION),
    dropped=("spec.stat_block()",),
)
def m6341a2(c: Cast) -> None:
    """The target line narrows by a type word, which `c.is_kind` does answer, so
    it is a gate in the body and not a marker. The zone it leaves behind is a
    block of its own described elsewhere; difficult terrain is all that can be
    laid without it."""
    if not c.is_kind("plant") and c.strike():
        c.hit()
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=True)


# --------------------------------------------------------------------------
# m6342
# --------------------------------------------------------------------------


@power(
    "m6342a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6342a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m6342a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d6", 4),
)
def m6342a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6342a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
)
def m6342a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6342a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m6342a3(c: Cast) -> None:
    """`c.summon` puts the creature in the initiative order as well as on the
    board, which is the second half of the printed sentence. The square is the
    one this creature is falling out of, read before it is lifted off."""
    c.summon("m6341", at=c.here)


# --------------------------------------------------------------------------
# m6505
# --------------------------------------------------------------------------


def _is_climbing(world: World, eid: int) -> bool:
    return moving_as(world, eid, "climb")


@power(
    "m6505a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6505a0(c: Cast) -> None:
    """`c.moving_as` is what a creature is doing now, held past the end of the
    move, which is the question "while climbing" asks -- `Movement.modes` only
    ever said what it could do."""
    me = c.me
    c.resist_forced(
        3, on=me, until=When.ENCOUNTER,
        when=lambda _ctx: moving_as(c.world, me, "climb"),
    )


@power(
    "m6505a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 8),
    dropped=("c.grab(dc=)",),
)
def m6505a1(c: Cast) -> None:
    """"Until the grab ends" is a lifetime no `When` measures. The printed escape
    DC is a fixed number the grab does not carry."""
    if c.strike():
        c.hit()
        victim = c.target
        c.grab()
        burn = c.ongoing(5, until=When.ENCOUNTER)
        if victim is not None:
            _until_escape(c, victim, burn)


@power(
    "m6505a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 6, kind=LIMITED),
    requires=_is_climbing,
    requires_text="it must be climbing",
)
def m6505a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6505a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6505a3(c: Cast) -> None:
    c.shift(c.speed_of())
    for victim in _holding(c):
        c.pull(10, on=victim)


# --------------------------------------------------------------------------
# m6603
# --------------------------------------------------------------------------


@power(
    "m6603a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 9),
)
def m6603a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6603a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 8),
)
def m6603a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6603a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m6603a2(c: Cast) -> None:
    c.resist(10, until=When.ENCOUNTER)


@power(
    "m6603a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6603a3(c: Cast) -> None:
    """Power, because that is the word the card prints in front of "bonus".
    Both modifiers belong to the handed-over blow and come off after it."""
    near = _press(c)
    if not near:
        return
    boost = c.bonus("attack", 4, on=c.me, until=When.EOT, kind="power")
    extra = c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT)
    try:
        c.basic(on=near[0])
    finally:
        c.end_effect(boost, why="the swing is over")
        c.end_effect(extra, why="the swing is over")


# --------------------------------------------------------------------------
# m6613
# --------------------------------------------------------------------------


def _shocked(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.dtype in (DamageType.LIGHTNING, DamageType.THUNDER)


@power(
    "m6613a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aura(difficult=)",),
)
def m6613a0(c: Cast) -> None:
    """The hold on shifting runs on the geometry rather than on the clock, so it
    is laid on entry and taken back on the way out. An aura cannot be difficult
    terrain: `c.zone` carries that and travels with nobody."""
    _denies_shift_in(c, c.aura(1, until=When.ENCOUNTER))


@power(
    "m6613a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 5),
)
def m6613a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)


@power(
    "m6613a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 6),
)
def m6613a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6613a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m6613a3(c: Cast) -> None:
    """Both named rows at the one creature, and no rider: the card says it uses
    them, not that anything happens if both land."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m6613a1", on=victim)
    c.use_power("m6613a2", on=victim)


@power(
    "m6613a4",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    trigger="it takes lightning or thunder damage",
    on=Trigger(DamageApplied, _shocked, "lightning or thunder damage lands on it"),
)
def m6613a4(c: Cast) -> None:
    """"Of the triggering type" is read off the event rather than guessed, which
    is the whole reason the trigger is declared on the damage and not on the
    hit that carried it."""
    dtype = getattr(c.trigger, "dtype", DamageType.LIGHTNING)
    for foe in _press(c):
        c.flat(5, dtype=dtype, on=foe)


# --------------------------------------------------------------------------
# m6627
# --------------------------------------------------------------------------


def _scorched(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.dtype is DamageType.RADIANT


@power(
    "m6627a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aura(difficult=)",),
)
def m6627a0(c: Cast) -> None:
    """The extra square is gated on both halves of the printed sentence at once:
    the creature bloodied, and the thing being shoved standing in the ring. An
    aura cannot be difficult terrain."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def in_the_ring(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or not _is_bloodied(c.world, me):
            return False
        return distance_between(c.world, me, foe) <= 1

    c.forces(1, on=me, until=When.ENCOUNTER, when=in_the_ring)


@power(
    "m6627a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6627a1(c: Cast) -> None:
    """"The next attack that hits it" is one blow, so the hold is swept the
    moment damage comes off hit points -- not on `Hit`, which is announced
    before the blow is paid and would end the vulnerability just in time for it
    to do nothing."""
    me = c.me

    def burned(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.RADIANT:
            return
        weak = c.vulnerable(5, until=When.EONT, on=me)
        if weak is None:
            return

        def spent(blow: DamageApplied) -> None:
            if blow.target == me and blow.dtype is not DamageType.RADIANT:
                c.world.effects.end(weak, "the blow has landed")

        c.watch(
            DamageApplied, spent, until=When.EONT, on=me, once=True,
            label=f"{c.ref} spent",
        )

    c.watch(DamageApplied, burned, until=When.ENCOUNTER, on=me, label=f"{c.ref} raw")


@power(
    "m6627a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 5),
)
def m6627a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6627a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6627a3(c: Cast) -> None:
    """The rider only exists when both swings went to one creature, so the row
    takes one target and throws the named attack at it twice."""
    victim = c.target
    if _both_hit(c, "m6627a2", "m6627a2") and victim is not None:
        c.push(1, on=victim)
        c.prone(on=victim)


@power(
    "m6627a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("Target.ongoing",),
)
def m6627a4(c: Cast) -> None:
    """"A creature taking ongoing fire damage" is a target line `Target` cannot
    express. Where the creature chosen does not qualify the row looks for one in
    reach that does rather than returning, which would be a minor action spent
    on a row that appears to have acted."""
    victim = c.target
    if victim is None or _ongoing_of(c, victim, DamageType.FIRE) == 0:
        victim = next(
            (f for f in _press(c) if _ongoing_of(c, f, DamageType.FIRE) > 0), None
        )
    if victim is not None:
        c.slide(1, on=victim)


# --------------------------------------------------------------------------
# m816
# --------------------------------------------------------------------------


@power(
    "m816a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 5),
)
def m816a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m816a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("query.moved_this_turn(world, eid)",),
)
def m816a1(c: Cast) -> None:
    """Two swings, which plays. The Requirement -- that it did not travel more
    than a square this round -- cannot be asked: nothing records what a creature
    has already done with its turn."""
    _two_basics(c, separate=False)


@power(
    "m816a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m816a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m839
# --------------------------------------------------------------------------


@power(
    "m839a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m839a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m839a1",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m839a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m839a2",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "an enemy misses it in melee"),
    attack=Attack(vs=FORT, printed=7),
)
def m839a2(c: Cast) -> None:
    """Aimed at whoever swung rather than at whatever the target line picked: a
    reaction routinely declares a target it never touches."""
    who = _triggering_enemy(c)
    if who is None or not c.adjacent(who):
        return
    if c.strike(on=who):
        c.slide(1, on=who)
        c.prone(on=who)


@power(
    "m839a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m839a3(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)
    _shrug_off_prone(c)


# --------------------------------------------------------------------------
# m888
# --------------------------------------------------------------------------


@power(
    "m888a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m888a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m888a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m888a1(c: Cast) -> None:
    """The row is its own attack line used twice, and the rider wants both on
    one creature -- so `ONE_CREATURE` rather than a spread, and the shove is
    paid only when the second landed too."""
    _two_swings(c, then=lambda: c.push(1))


@power(
    "m888a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "a melee attack hits it"),
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m888a2(c: Cast) -> None:
    """"If the attacker is within reach" is the printed condition and is asked
    of the attacker rather than of the target line."""
    who = _triggering_enemy(c)
    if who is None or not c.adjacent(who):
        return
    if c.strike(on=who):
        c.hit(on=who)
