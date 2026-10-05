"""Monster abilities, level 1, brutes: the second sweep.

Fourteen stat blocks whose rows were still undeclared, including two solos and
two elites. `brutes.py` holds the first sweep of this level; the split is by
*when* the work was done rather than by what the creatures are, and the
conventions are the ones that file settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=6)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a printed "crit NdX + n" line **replaces** the damage rather than adding to
  it, and it is a roll -- so it is applied flat, past the engine's own rule
  that a critical maxes the declared dice;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`.

The four helpers imported from `artillery_sa.py` are the sentences the two
roles share word for word.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _cheb,
    _is_bloodied,
    _recharge_when_bloodied,
    _runners,
    _sure_footed_shift,
)
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.skirmishers import _advantage_rider
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Effect,
    Health,
    Keyword,
    Melee,
    Ranged,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    ConditionEnded,
    Dropped,
    Hit,
    Miss,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import flanked_by, squares
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_opportunity,
    closed_on_me,
    targets_me,
)

#: The label the dormant state is held under. Two rows on the same stat block
#: have to agree on it: one lays it, the other ends it.
_STILL = "m5449a0"


def _crit_line(c: Cast, dice: str, bonus: int) -> None:
    """A printed "crit NdX + n" line.

    It *replaces* the damage rather than adding to it, and it is a roll -- so
    it is applied flat, past the engine's own rule that a critical maxes the
    declared dice, which would read the wrong number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus)
    else:
        c.hit()


def _shattered(c: Cast) -> None:
    """A critical hit puts this creature down whatever its hit points are.

    Paid as damage equal to whatever it has left rather than by writing to
    `Health`, so the drop goes through `ecs.damage` and `Dropped` is announced
    the one way everything else announces it -- which is what the other row on
    one of these blocks is listening for.
    
    **Approximated, and marked.** `c.flat` goes through `deal_damage`, so the
    blow is absorbed by temporary hit points and stopped outright by resist-all
    -- and the card says "reduced to 0 hit points" with no condition. Paying it
    as damage is right about the common case and wrong about the creature that
    has been given temp hp, which is why the tree's other rows of this shape
    carry `c.kill()` and these now do too. Two readings of one sentence cannot
    both be right.
    """
    me, ref = c.me, c.ref

    def struck(ev: Hit) -> None:
        if ev.target != me:
            return
        result = getattr(ev, "result", None)
        if not (result is not None and result.critical):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{ref} brittle")


def _felled_by_a_crit(c: Cast) -> bool:
    """Was the blow that put this creature down a critical?

    `Dropped` carries who struck it and not how, and two rows on one of these
    blocks print opposite halves of that sentence -- so the question is
    answered off the log, which is the only record of the swing left by the
    time the creature is down. The most recent `Hit` on it is the blow.
    """
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, Hit) and ev.target == c.me:
            result = getattr(ev, "result", None)
            return bool(result is not None and result.critical)
        if isinstance(ev, Miss) and ev.target == c.me:
            return False
    return False


def _step_toward(c: Cast, who: int) -> bool:
    """Shift one square closer to somebody.

    `c.shift(toward=)` does not exist, so the destination is picked here: of
    the eight squares one step away, whichever closes the gap and closes it
    most. Falls through to nothing when the creature is already as close as it
    can get, which is the honest answer rather than a shift to anywhere.
    """
    theirs = squares(c.world, who)
    if not theirs:
        return False
    here = c.here

    def gap(sq: Square) -> int:
        return min(_cheb(sq, t) for t in theirs)

    nearer = [
        (x, y)
        for x in range(here[0] - 1, here[0] + 2)
        for y in range(here[1] - 1, here[1] + 2)
        if (x, y) != here and gap((x, y)) < gap(here)
    ]
    return any(c.shift(1, to=square) for square in sorted(nearer, key=gap))


def _still(c: Cast) -> Effect | None:
    return next((e for e in c.world.effects.of(c.me) if e.label == _STILL), None)


# --------------------------------------------------------------------------
# m115928
# --------------------------------------------------------------------------


@power(
    "m115928a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def m115928a0(c: Cast) -> None:
    """Whoever is riding it is read when the blow lands, not when the trait
    arms: nobody is mounted at the start of a fight, so a bonus laid on the
    rider then would be laid on nobody and stay there."""
    me, ref = c.me, c.ref

    def charged(ev: Hit) -> None:
        if ev.attacker != c.rider() or not getattr(ev, "charge", False):
            return
        c.flat(3, on=ev.target)

    c.watch(Hit, charged, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m115928a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 4),
)
def m115928a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115928a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(0),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m115928a2(c: Cast) -> None:
    """`c.overrun` is the only thing that walks through occupied squares and
    then says who it passed; `c.move` refuses one and reports nothing. The list
    it returns is each enemy once, which is what "the first time it enters that
    enemy's space" means."""
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


# --------------------------------------------------------------------------
# m1437
# --------------------------------------------------------------------------


@power(
    "m1437a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 4, dtype=DamageType.COLD),
)
def m1437a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1437a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 4),
)
def m1437a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1437a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
)
def m1437a2(c: Cast) -> None:
    """Two of the untyped attack and then the cold one, which is the pairing
    the block's two at-will damage lines make: one of them is the cold line and
    that is the one held back for whoever took both of the others.

    `c.landed` reads the borrowed row's own result, which is what "if it hits a
    single target with both" is asking, counted rather than and-ed so the
    second swing is still made when the first missed.
    """
    foe = c.target
    if foe is None:
        return
    landed = 0
    for _ in range(2):
        if c.use_power("m1437a1", on=foe) and c.landed:
            landed += 1
    if landed == 2:
        c.use_power("m1437a0", on=foe)


@power(
    "m1437a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=2),
    damage=Damage("3d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m1437a3(c: Cast) -> None:
    """"Save ends both" is one effect with two conditions and exactly one
    saving throw -- applied separately it would be two saves against a thing
    the card says is one."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4230
# --------------------------------------------------------------------------


@power(
    "m4230a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d4", 3),
)
def m4230a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# --------------------------------------------------------------------------
# m4457
# --------------------------------------------------------------------------


@power(
    "m4457a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 3),
)
def m4457a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4457a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="immobilized creature"),
    attack=Attack(vs=AC, printed=4),
    damage=Damage("2d6", 3),
    requires=_any_enemy_suffering(Condition.IMMOBILIZED),
    requires_text="must have an immobilized creature to aim at",
    dropped=("Target.kind",),
)
def m4457a1(c: Cast) -> None:
    """The restriction is asked in the body, since `Target` filters on side and
    size and not on what a creature is suffering; the loss is that the action
    menu offers the row against anybody. The hold is lifted whatever laid it,
    which is what the card says -- it does not name its own."""
    if not c.is_(Condition.IMMOBILIZED):
        return
    if c.strike():
        c.hit()
        c.cure(Condition.IMMOBILIZED)


@power(
    "m4457a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,

    dropped=("c.kill()",),)
def m4457a2(c: Cast) -> None:
    _shattered(c)


# --------------------------------------------------------------------------
# m4503
# --------------------------------------------------------------------------


@power(
    "m4503a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage(bonus=5, kind=MINION),
)
def m4503a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4503a1",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger="one of its own drops to 0 hit points",
    on=Trigger(Dropped, lambda world, me, ev: ev.actor != me, "one of its own falls"),
    dropped=("spec.ref",),
)
def m4503a1(c: Cast) -> None:
    """The step toward the fallen is what plays. The other half of the printed
    Effect is "and rolls to recharge" a second row, and the extraction names
    that row nowhere on the card -- so there is no ref to restore a use of and
    `spec.ref` is the gap. Guessing one would spend a use of whichever row the
    guess landed on.

    The trigger is narrowed here rather than in the predicate, because "one of
    its own" is an `Ident.ref` match and no ready-made predicate asks that.
    """
    fallen = getattr(c.trigger, "actor", None)
    if fallen is None or _ref_of(c, fallen) != _ref_of(c, c.me):
        return
    if c.distance(fallen) <= 5:
        _step_toward(c, fallen)


# --------------------------------------------------------------------------
# m4615
# --------------------------------------------------------------------------


@power(
    "m4615a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d12", 4),
)
def m4615a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 16)


@power(
    "m4615a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 3),
)
def m4615a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4615a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d12", 4, kind=LIMITED),
)
def m4615a2(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 16)
        c.dazed(until=When.EONT)


@power(
    "m4615a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d12", 4),
)
def m4615a3(c: Cast) -> None:
    """Creatures in the burst, not enemies: it catches its own side as readily
    as anybody's, which is what the card says."""
    if c.strike():
        _crit_line(c, "1d12", 16)


@power(
    "m4615a4",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m4615a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m4615a5",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an opportunity attack",
    on=Trigger(
        Hit, both(targets_me, by_opportunity), "an enemy hits it with an opening"
    ),
)
def m4615a5(c: Cast) -> None:
    """The triggering enemy is read off the event rather than off a target
    line: this row declares none, so `ev.attacker` is the only thing that names
    the creature that swung."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        c.basic(on=attacker)


# --------------------------------------------------------------------------
# m4759
# --------------------------------------------------------------------------


@power(
    "m4759a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 7),
)
def m4759a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4759a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m4759a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4759a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4759a2(c: Cast) -> None:
    """One swing from each of the two weapon rows, borrowed rather than copied
    so their numbers stay in one place, and the four extra is flat because the
    card adds it to the pair rather than to either damage line."""
    foe = c.target
    if foe is None:
        return
    landed = 0
    for ref in ("m4759a0", "m4759a1"):
        if c.use_power(ref, on=foe) and c.landed:
            landed += 1
    if landed == 2:
        c.flat(4, on=foe)


@power(
    "m4759a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("2d6", 2, kind=LIMITED),
)
def m4759a3(c: Cast) -> None:
    """One element for the whole blast, chosen once and then applied to every
    creature in it -- so the loop is run from the first target and the later
    calls return, rather than asking again per target and dealing four
    different kinds of damage out of one printed sentence.

    The header's damage line is untyped, because the card's is "Varies"; the
    body deals the typed version instead of calling `c.hit`, so nothing is
    applied twice.

    "Save ends both" is one save for three things, so the burn is the anchor
    and the two penalties are ended off its `on_end` -- laid on their own they
    would each be rolled against separately.
    """
    if not c.first:
        return
    elements = [
        DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
    ]
    element = c.choose(elements, "which element") or DamageType.COLD
    for foe in list(c.targets):
        if not c.strike(on=foe):
            continue
        c.damage("2d6", 2, dtype=element, on=foe)
        burn = c.ongoing(5, element, on=foe)
        soft = [
            c.penalty(AC, 2, until=When.ENCOUNTER, on=foe),
            c.penalty(FORT, 2, until=When.ENCOUNTER, on=foe),
        ]
        if burn is not None:
            burn.on_end.append(
                lambda held=soft: [
                    c.world.effects.end(part, c.ref) for part in held if part is not None
                ]
            )


@power(
    "m4759a4",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, by_me, "it makes an attack roll"),
)
def m4759a4(c: Cast) -> None:
    """"He must use the second roll, even if it is lower" is `keep="new"`."""
    c.reroll_attack(keep="new")


@power(
    "m4759a5",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4759a5(c: Cast) -> None:
    """Every attack, which is what the card says -- no range is named, so the
    rider is not narrowed to melee."""
    _advantage_rider(c, "1d6")


@power(
    "m4759a6",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4759a6(c: Cast) -> None:
    """Both halves read off the `Hit`: `charge` rides on it as a plain
    attribute and the advantage is on the live `AttackResult`, which is the only
    place it can still be asked -- `has_combat_advantage` is already false by
    then, because a one-shot grant has been spent."""
    me, ref = c.me, c.ref

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if not (getattr(ev, "charge", False) or c.had_advantage(ev)):
            return
        c.ongoing(5, on=ev.target)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m4759a7",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4759a7(c: Cast) -> None:
    _sure_footed_shift(c)


# --------------------------------------------------------------------------
# m5283
# --------------------------------------------------------------------------


@power(
    "m5283a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5283a0(c: Cast) -> None:
    _runners(c, "m5283")


@power(
    "m5283a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 5),
)
def m5283a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5283a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("4d6", 4, kind=LIMITED),
)
def m5283a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()


@power(
    "m5283a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("4d6", 4, kind=LIMITED),
    requires=_is_bloodied,
    requires_text="must be bloodied",
)
def m5283a3(c: Cast) -> None:
    """Vulnerable to everything, so no type is named -- `c.vulnerable` with no
    `dtype` writes the amount against every one of them."""
    if c.strike():
        c.hit()
        c.vulnerable(5, until=When.EONT)


# --------------------------------------------------------------------------
# m5413
# --------------------------------------------------------------------------


@power(
    "m5413a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5413a0(c: Cast) -> None:
    """`c.reanimate` is the verb: `_die` leaves the body an entity and only
    lifts it off the grid, so standing it back up is a matter of giving it a
    square again, and one hit point is the number this is worth. The hold runs
    to the end of its next turn, which is when the card says it falls."""
    me = c.me

    def fell(ev: Dropped) -> None:
        if ev.actor == me:
            c.reanimate(on=me, hp=1, until=When.EONT)

    c.watch(
        Dropped, fell, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} not yet",
    )


@power(
    "m5413a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5413a1(c: Cast) -> None:
    """A bonus that *counts* something, which `c.bonus` cannot hold: its value
    is fixed when the modifier is laid, and this one changes with every step
    anybody takes. So it is paid as the blow lands, which comes to the same
    total on the same swing.

    The attack row on this block prints the same sentence again as a reminder of
    this trait. It is implemented here, once, so one printed bonus is not paid
    twice.
    """
    me, ref = c.me, c.ref

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        crowd = sum(1 for a in c.allies() if c.adjacent_to(a, ev.target))
        if crowd:
            c.flat(crowd, on=ev.target)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5413a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=5, kind=MINION),
)
def m5413a2(c: Cast) -> None:
    """The extra damage per adjacent ally is the trait on this block and is
    paid there, not here -- written in both places it would be paid twice for
    one printed sentence."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5448
# --------------------------------------------------------------------------


@power(
    "m5448a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,

    dropped=("c.kill()",),)
def m5448a0(c: Cast) -> None:
    _shattered(c)


@power(
    "m5448a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d12", 3),
)
def m5448a1(c: Cast) -> None:
    """Grabbed by anybody, which is what the card says -- it does not ask whose
    hold it is."""
    if not c.strike():
        return
    if c.is_(Condition.GRABBED):
        c.damage("1d12", 8)
    else:
        c.hit()


@power(
    "m5448a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6", 3),
)
def m5448a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    if not c.grabbing():
        c.grab()


@power(
    "m5448a3",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points, but not by a critical hit",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5448a3(c: Cast) -> None:
    """"But not by a critical hit" is the half the event cannot answer, so it is
    read off the log -- see `_felled_by_a_crit`. The other row on this block is
    the sentence this one excepts, which is why the two have to agree."""
    if _felled_by_a_crit(c):
        return
    if c.roll("1d20") >= 15:
        c.reanimate(on=c.me, hp=1)


# --------------------------------------------------------------------------
# m5449
# --------------------------------------------------------------------------


@power(
    "m5449a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.restrict_action()", "c.immune(ongoing=)"),
)
def m5449a0(c: Cast) -> None:
    """It stops being a creature and starts being scenery whenever nothing is
    standing next to it. Four of the five halves are sayable: resist 10 to
    everything, immunity to every condition, immunity to forced movement
    (`c.resist_forced` with a number no shove reaches, which is what immunity to
    one is), and immunity to three damage types -- written straight onto
    `Defences.immune` with an undo, the way `c.vulnerable` writes the mirror of
    it, because `c.immune` takes conditions and nothing takes a damage type.

    Dropped: it also takes no standard, move or minor action while dormant, and
    nothing restricts an action by name -- `Condition.PETRIFIED` would do it and
    also make the creature helpless, which the card does not say and which is a
    much worse bargain than the one it offers. And immunity to ongoing damage,
    which no verb grants either; with resist 10 standing, a level-one burn gets
    through none of it anyway, but that is arithmetic rather than the rule.

    The sub-effects are held together and ended off the state's own `on_end`,
    so the row that wakes the creature up has one thing to end.
    """
    me, ref = c.me, c.ref

    def settle(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or _still(c) is not None:
            return
        if any(c.adjacent(foe) for foe in c.enemies()):
            return
        hold = c.effect(_STILL, until=When.ENCOUNTER, on=me)
        if hold is None:
            return
        parts = [
            c.resist(10, until=When.ENCOUNTER, on=me),
            c.resist_forced(99, until=When.ENCOUNTER, on=me),
            c.immune(*Condition, until=When.ENCOUNTER, on=me),
        ]
        shell = c.world.get(me, Defences) or c.world.add(me, Defences())
        shut = [
            kind
            for kind in (DamageType.NECROTIC, DamageType.POISON, DamageType.PSYCHIC)
            if kind not in shell.immune
        ]
        shell.immune.update(shut)

        def wake() -> None:
            for part in parts:
                if part is not None:
                    c.world.effects.end(part, ref)
            for kind in shut:
                shell.immune.discard(kind)

        hold.on_end.append(wake)

    c.watch(TurnStart, settle, until=When.ENCOUNTER, on=me, label=f"{ref} settles")


@power(
    "m5449a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=5, kind=MINION),
)
def m5449a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5449a2",
    level=1,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=3),
    damage=Damage(bonus=3, kind=MINION),
    trigger="an enemy enters a square adjacent to it while it is dormant",
    on=Trigger(AdjacencyGained, closed_on_me, "an enemy steps up to it"),
)
def m5449a2(c: Cast) -> None:
    """`closed_on_me` rather than a bare adjacency check: `AdjacencyGained`
    carries `mover`, so the creature's own approach does not set this off -- and
    a dormant one cannot approach anything anyway, which is the point of the
    gate above it.

    Waking up is the Effect and happens whether the swing lands, so the state
    is ended outside the hit branch.
    """
    hold = _still(c)
    if hold is None:
        return
    foe = getattr(c.trigger, "mover", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        if not c.grabbing():
            c.grab(on=foe)
    c.world.effects.end(hold, c.ref)


# --------------------------------------------------------------------------
# m5568
# --------------------------------------------------------------------------


@power(
    "m5568a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5568a0(c: Cast) -> None:
    """`crit_range` is read as `20 - crit_range`, so three is the printed
    17-20. Asked inside the gate, because the creature is not bloodied when the
    trait arms and a bonus fixed then would never arrive."""
    c.bonus(
        "crit_range", 3, until=When.ENCOUNTER, on=c.me,
        when=lambda ctx: c.bloodied(c.me),
    )


@power(
    "m5568a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d12", 11, dtype=DamageType.COLD),
)
def m5568a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5568a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d12", 4),
)
def m5568a2(c: Cast) -> None:
    """"Twice against that creature" is the same swing made again when there is
    only one target, read off `c.targets` -- which is the whole target list of
    this one use and the only thing that can answer how many were picked."""
    if c.strike():
        c.hit()
    if len(c.targets) == 1 and c.strike():
        c.hit()


@power(
    "m5568a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d8", 4, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5568a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5568a4",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("1d12", 4),
    trigger="an enemy hits it while flanking it",
    on=Trigger(
        Hit,
        lambda world, me, ev: (
            getattr(ev, "target", None) == me
            and flanked_by(world, me, getattr(ev, "attacker", -1))
        ),
        "an enemy hits it while flanking it",
    ),
)
def m5568a4(c: Cast) -> None:
    """Flanking is a fact about three positions, so it is asked of the board in
    the predicate rather than read off the event -- nothing an attack announces
    says where the attacker's friends are standing."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(3, on=foe)


@power(
    "m5568a5",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m5568a5(c: Cast) -> None:
    """`c.restore_use` then `c.use_power`: the card hands the breath back and
    fires it in one free action, and spending the restored use is what makes
    the row cost something afterwards."""
    c.restore_use("m5568a3", on=c.me)
    c.use_power("m5568a3")


# --------------------------------------------------------------------------
# m6562
# --------------------------------------------------------------------------


@power(
    "m6562a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=5, kind=MINION),
    dropped=("c.contract(ref)",),
)
def m6562a0(c: Cast) -> None:
    """The saving throw is made "at the end of the encounter" and what it
    decides is which stage of a disease the target wakes up on, which is a
    track the engine does not keep and which the card names no ref for. The
    damage is the half that plays."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m994
# --------------------------------------------------------------------------


@power(
    "m994a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("3d4", 2),
)
def m994a0(c: Cast) -> None:
    """A trade the attacker chooses: two of the three dice for a fall. Offered
    as the creature's own decision -- `who=c.me`, because `c.may` follows the
    target otherwise -- and taken by default, since the other trait on this
    block pays 2d4 back against a prone target and the swarm is giving up
    nothing."""
    if not c.strike():
        return
    if c.may("give up 2d4 of the damage to knock it down", who=c.me):
        c.damage("1d4", 2)
        c.prone()
    else:
        c.hit()


@power(
    "m994a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("1d4", 1),
)
def m994a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m994a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m994a2(c: Cast) -> None:
    """Standing up is announced as `ConditionEnded` on prone with `why` set by
    `actions.perform`, and nothing else announces it at all. `c.arm_trigger`
    rather than `c.watch`, because an opening costs the creature its
    opportunity action and a bare watch is free -- which is the one way an
    armed reaction differs from a declared one."""
    me = c.me

    def stood(ev: ConditionEnded) -> bool:
        return (
            ev.condition is Condition.PRONE
            and ev.why == "stood up"
            and ev.target != me
            and ev.target in c.enemies()
            and c.adjacent(ev.target)
        )

    c.arm_trigger(
        ConditionEnded,
        lambda ev: c.basic(on=ev.target),
        when=stood,
        cost=OPPORTUNITY,
        until=When.ENCOUNTER,
        on=me,
        label=f"{c.ref} underfoot",
    )


@power(
    "m994a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m994a3(c: Cast) -> None:
    """A rolled rider, which `c.bonus` says with `dice=` and a value of nought
    -- the card adds dice rather than a number."""

    def floored(ctx: dict[str, object]) -> bool:
        who = ctx.get("target")
        return isinstance(who, int) and c.is_(Condition.PRONE, on=who)

    c.bonus("damage", 0, dice="2d4", until=When.ENCOUNTER, on=c.me, when=floored)
