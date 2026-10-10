"""Monster abilities, level 2, brutes: the second sweep.

Twenty stat blocks whose rows were still undeclared. `brutes.py` holds the
first sweep of this level; the split is by *when* the work was done rather
than by what the creatures are, and the conventions are the ones that file and
the level-1 sweep settled:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=5)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold
  it for the rest of the fight;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`.

Five helpers come from `artillery_sa.py` beside this file and two from
`brutes.py`: four printed sentences are word for word the same on blocks of
both roles, and "+1 damage per ally of its own kind pressed against the
target" was already written once.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _is_bloodied,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_02.artillery_sa import (
    ALL_DEFENCES,
    _minor_shift,
    _saves_off_prone,
    _trap_shield,
)
from combat_engine.content.monsters.level_02.brutes import _crowd, _same_row
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
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
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    RelationCleared,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    enemy_within,
    hits_me,
    not_critical,
    targets_me,
)

#: The two holds m4225a3 reads. Written out because the printed line names
#: them as a pair and both have to be asked of the attack context.
STUCK = (Condition.SLOWED, Condition.IMMOBILIZED)


def _clings_on(c: Cast, then: Any = None) -> None:
    """"On a 15 or higher it is instead reduced to 1 hit point."

    Two blocks print this. `Dropped` is announced once the creature is already
    down, and the dispatcher offers a row to a creature answering its *own*
    downfall -- so the body runs; what it has to do is put a hit point back.
    A creature that is dying still has `Health`, so a heal reaches it; a minion
    is dead outright and wants `c.reanimate`, which gives the corpse a square
    again.
    """
    if c.roll("1d20") < 15:
        return
    if then is not None:
        then()
    if alive(c.world, c.me):
        c.heal(1, on=c.me)
    else:
        c.reanimate(on=c.me, hp=1)


def _allies_pressing(c: Cast, victim: int) -> int:
    """How many of its allies are adjacent to that creature. The caster is
    left out: the printed line is a bonus *per ally*, and it is not its own."""
    return sum(1 for friend in c.within(1, of=victim, side="ally") if friend != c.me)


# --------------------------------------------------------------------------
# m1008
# --------------------------------------------------------------------------


@power(
    "m1008a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6", 3),
)
def m1008a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1008a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m1008a1(c: Cast) -> None:
    """The printed sentence is about the *ally's* reaction, but it only ever
    happens because this creature charges -- so the row is the charge, and the
    second runner is handed one at the same target.

    `charges=True` or the engine measures a sword's reach before the run and
    refuses the row in every situation a charge is for.
    """
    victim = c.target
    if victim is None:
        return
    c.charge_at(victim)
    friend = next(
        (
            other
            for other in c.within(5, side="ally")
            if _same_row(c, other, "m1008") and alive(c.world, other)
        ),
        None,
    )
    if friend is not None:
        c.charge_at(victim, who=friend)


# --------------------------------------------------------------------------
# m1991
# --------------------------------------------------------------------------


@power(
    "m1991a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d8", 8),
)
def m1991a0(c: Cast) -> None:
    """The critical damage is the engine's -- `c.damage` maxes its dice on a
    crit, which is the printed number.

    The disease is written: `c.contract` records it and `#389` built the
    table the ref resolves to. **The stage never advances in a fight**,
    which is the card -- every disease page checks at the end of an
    extended rest, and this engine has none."""
    if c.strike():
        c.hit()
        c.contract("x5_45")


@power(
    "m1991a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1991a1(c: Cast) -> None:
    """The +2 to AC and Fortitude is **already in the database numbers**, so
    arming this adds nothing and being bloodied has to take it back off. The
    vulnerability is the other way round: it is in the numbers too and the
    trait suppresses it until the line is crossed.

    **The infection is on a critical hit by this creature**, so it is a
    watcher on its own hits rather than a clause in any one attack row --
    every attack it makes can crit, and the trait is where the card prints
    it. `x5_45` is a row since #389; `m1991a0` carries the same clause on its
    own hit line, which is the ordinary half.

    `once=True` is deliberately **not** on this watch, unlike the bloodied
    one below: the hide stops working once, and a creature can crit more
    than once.
    """
    me = c.me
    guard = c.world.get(me, Defences) or c.world.add(me, Defences())
    held = guard.vulnerable.pop(DamageType.RADIANT, 0)

    def crit(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            c.contract("x5_45", on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=me, label=f"{c.ref} infects")

    def bled(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        if held:
            guard.vulnerable[DamageType.RADIANT] = held
        c.penalty(AC, 2, on=me, until=When.ENCOUNTER)
        c.penalty(FORT, 2, on=me, until=When.ENCOUNTER)

    c.watch(
        Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} hide"
    )


# --------------------------------------------------------------------------
# m3270
# --------------------------------------------------------------------------


@power(
    "m3270a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m3270a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3270a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d8", 5, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m3270a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        for which in ALL_DEFENCES:
            c.penalty(which, 2, until=When.SAVE_ENDS)


@power(
    "m3270a2",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m3270a2(c: Cast) -> None:
    """"When first bloodied" is written as an entry requirement, not a declared
    trigger: a minor action has no trigger window -- `WINDOW_OF` covers the
    immediate actions, free and none -- so a `Trigger` laid here would never be
    armed and the row would look finished and be inert. Being an encounter
    power is what makes it happen once.
    """
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)
    c.regeneration(2, on=c.me, until=When.ENCOUNTER, while_bloodied=True)


# --------------------------------------------------------------------------
# m3563
# --------------------------------------------------------------------------


@power(
    "m3563a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
)
def m3563a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3563a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
)
def m3563a1(c: Cast) -> None:
    """No damage at all -- the whole hit is the hold. The -5 is laid on the
    creature being held and is read by `escape.attempt` through the same
    modifier table a skill check uses."""
    if c.strike():
        c.grab()
        c.penalty("escape", 5, until=When.ENCOUNTER)


@power(
    "m3563a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3563a2(c: Cast) -> None:
    """A critical hit against it drops it to 0 hit points, whatever it had.

    `c.kill` and not a very large blow: the card sets no condition, and damage
    is absorbed by temporary hit points, halved by being insubstantial and
    stopped outright by resist-all. `critical=True` is carried onto `Dropped`
    for the rows that ask whether a critical did it.
    """
    me = c.me

    def shattered(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.kill(on=me, critical=True)

    c.watch(Hit, shattered, until=When.ENCOUNTER, on=me, label=f"{c.ref} brittle")


# --------------------------------------------------------------------------
# m4225
# --------------------------------------------------------------------------


@power(
    "m4225a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m4225a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4225a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=3),
)
def m4225a1(c: Cast) -> None:
    """Asked before the row's own slow lands: afterwards every target is
    "already slowed" and the line escalates every single time."""
    stuck = c.is_(Condition.SLOWED)
    if not c.strike():
        return
    if stuck:
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4225a2",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m4225a2(c: Cast) -> None:
    c.shift(3)


@power(
    "m4225a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4225a3(c: Cast) -> None:
    """A gate on the attack context rather than an effect put on and taken off
    around every slow: the modifier is asked at the moment the roll is made,
    which is the only time the answer is knowable."""

    def pinned(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and any(c.is_(cond, on=victim) for cond in STUCK)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=pinned)


# --------------------------------------------------------------------------
# m4717
# --------------------------------------------------------------------------


@power(
    "m4717a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d12", 3),
)
def m4717a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4717a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    no_provoke=True,
    dropped=("compendium.attack_defence",),
)
def m4717a1(c: Cast) -> None:
    """The row's own printed attack line has **no defence** -- "+3 vs or
    (whichever is lower)" -- which is a defect in the compendium rather than
    anything to invent a defence for (#360). The content of the power is the
    two rays below, and each of those prints its own defence, so the row plays
    and only the garbled header line is missing.

    Two branches with two defences, which is what `attack_alt` holds, except
    that the choice is a die rather than the user's -- so it is rolled here.
    """
    bonus = c.world.scaling.trim(4, c.level)
    foes = [foe for foe in c.enemies() if c.distance(foe) <= 5 and c.can_see(foe)]
    if not foes:
        return
    victim = foes[0]
    if c.roll("1d2") == 1:
        if c.attack(bonus, REF, on=victim):
            c.damage("1d6", 3, dtype=DamageType.FIRE, on=victim)
    elif c.attack(bonus, FORT, on=victim):
        c.damage("1d6", dtype=DamageType.NECROTIC, on=victim)
        c.weakened(until=When.EONT, on=victim)


@power(
    "m4717a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m4717a2(c: Cast) -> None:
    """The step is once for the whole power, not once per target: `c.last`
    rather than `c.first`, because it is printed after the attacks."""
    if c.strike():
        c.hit()
    if c.last:
        c.shift(3)


@power(
    "m4717a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m4717a3(c: Cast) -> None:
    """The Effect is once for the whole power and comes after the burst, so it
    hangs off `c.last`. The secondary swing is rolled here rather than declared
    as `attack_alt`: an alt branch is a *choice* between two lines and this is
    a second attack in the same use.
    """
    if c.strike():
        c.hit()
        c.push(1)
    if not c.last:
        return
    c.forbid("m4717a5", on=c.me, until=When.SAVE_ENDS)
    c.shift(c.roll("1d4"))
    bonus = c.world.scaling.trim(5, c.level)
    near = c.within(1, side="enemy")
    if near and c.attack(bonus, AC, on=near[0]):
        c.damage("2d10", 3, on=near[0])
        c.stunned(until=When.EONT, on=near[0])


@power(
    "m4717a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4717a4(c: Cast) -> None:
    """"Cumulative" is the whole point: untyped modifiers add, so a fresh
    penalty and bonus each turn is the printed arithmetic and `stacks=True` --
    the default -- is what makes it so."""
    me, ref = c.me, c.ref

    def opened(ev: TurnStart) -> None:
        if ev.actor != me or not _is_bloodied(c.world, me):
            return
        c.restore_use("m4717a3", on=me)
        c.penalty("attack", 1, on=me, until=When.ENCOUNTER)
        c.bonus("damage", 1, on=me, until=When.ENCOUNTER)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{ref} frenzy")


@power(
    "m4717a5",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m4717a5(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4719
# --------------------------------------------------------------------------


@power(
    "m4719a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 5, kind=MINION),
)
def m4719a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4719a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 6, kind=MINION),
)
def m4719a1(c: Cast) -> None:
    """It goes off whether the swing lands or not, which is why the last line
    is outside the hit branch. One point is the whole of a minion's hit points,
    so that is what "drops to 0" costs here -- and `c.flat` is the right verb
    because it is damage the creature does to itself, not a condition.
    """
    victim = c.target
    if victim is None:
        return
    c.charge_at(victim, c.ref)
    if c.landed:
        c.immobilized(until=When.EOTNT, on=victim)
        c.grants_advantage(to="team", until=When.EOTNT, on=victim)
    c.flat(1, on=c.me)


# --------------------------------------------------------------------------
# m5358
# --------------------------------------------------------------------------


@power(
    "m5358a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5358a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m5358a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5358a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m5358a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 6),
)
def m5358a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.push(1)
            c.prone()


@power(
    "m5358a3",
    level=2,
    usage=Usage.RECHARGE,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
)
def m5358a3(c: Cast) -> None:
    """No recharge number: the printed line is "recharge when the chosen enemy
    drops", and nothing else puts it back -- so the field stays 0 and the watch
    below is the only way the row returns.

    "One enemy it can see" prints no range, and `PERSONAL` is not the way to
    say that -- `candidates` finds nobody at all there, so the row was never
    offered. A long `Ranged` is the nearest honest reading of line of sight.

    The chosen enemy is a relation rather than a closure, so "until it uses
    this power again" is said by ending the previous hold; the bonus itself is
    laid once and reads the relation each time a blow is rolled.
    """
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.of(me)):
        if eff.label in (f"{ref} quarry", f"{ref} hunt"):
            c.world.effects.end(eff, "chose another")
    c.quarry(on=victim, until=When.ENCOUNTER)
    c.effect(f"{ref} hunt", until=When.ENCOUNTER, on=me)
    c.bonus(
        "damage",
        5,
        on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: not ctx.get("ranged") and c.is_quarry(ctx.get("target")),
    )

    def fell(ev: Dropped) -> None:
        if ev.actor == victim:
            c.restore_use(ref, on=me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} paid")


# --------------------------------------------------------------------------
# m5399
# --------------------------------------------------------------------------


@power(
    "m5399a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d10", 4),
)
def m5399a0(c: Cast) -> None:
    """Bloodied is asked *before* the blow: the printed condition is how the
    target stood when it was struck, and a creature taken below the line by
    this very hit was not bloodied when the claw came in."""
    hurt = _is_bloodied(c.world, c.target) if c.target is not None else False
    if c.strike():
        c.hit()
        if hurt:
            c.heal(3, on=c.me)


@power(
    "m5399a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one bloodied creature",
        bloodied=True,
    ),
    once_per_round=True,
    attack=Attack(vs=FORT, printed=8),
)
def m5399a1(c: Cast) -> None:
    """No damage line: knocking the creature down is the whole of the hit."""
    if c.strike():
        c.prone()


@power(
    "m5399a2",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when an adjacent enemy is first bloodied",
    on=Trigger(Bloodied, enemy_within(1), "an adjacent enemy is first bloodied"),
)
def m5399a2(c: Cast) -> None:
    """`Bloodied` names its subject `actor`, which is what `enemy_within`
    measures from -- so the predicate is about the creature that just crossed
    the line and not about whoever pushed it over."""
    victim = getattr(c.trigger, "actor", None)
    if victim is not None:
        c.use_power("m5399a0", on=victim)


# --------------------------------------------------------------------------
# m5462
# --------------------------------------------------------------------------


@power(
    "m5462a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5462a0(c: Cast) -> None:
    """Read off the damage that was actually applied rather than off the attack
    that carried it: the printed line is about taking cold damage, which
    ongoing cold and a hazard both do and no attack announces."""
    me = c.me

    def chilled(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.COLD and ev.amount > 0:
            c.slowed(on=me, until=When.EONT)

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=me, label=f"{c.ref} chill")


@power(
    "m5462a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE),
)
def m5462a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5462a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5462a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5462a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=3),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE, kind=LIMITED),
    trigger="when it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5462a3(c: Cast) -> None:
    """A death throe. The dispatcher offers a row to a creature answering its
    own downfall, so this fires from the floor; "the creature is destroyed" is
    already true and needs nothing said.

    "This ongoing fire damage ignores the resistance the petrified condition
    provides" sits on the *dealer*, which is this creature, so it is armed once
    rather than per target.
    """
    if c.first:
        c.ignore_resistance(dtype=DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.condition(Condition.PETRIFIED, until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.FIRE)


# --------------------------------------------------------------------------
# m5536
# --------------------------------------------------------------------------


@power(
    "m5536a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5536a0(c: Cast) -> None:
    """"Enters the aura" is one event per arrival, which is exactly what
    `AdjacencyGained` is -- a creature that stands still inside it is not
    entering and takes nothing more."""
    from combat_engine.engine.events import AdjacencyGained

    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def arrived(ev: AdjacencyGained) -> None:
        if ev.other != me or team(c.world, ev.actor) is team(c.world, me):
            return
        c.flat(2, on=ev.actor)

    for foe in c.within(1, side="enemy"):
        c.flat(2, on=foe)
    c.watch(
        AdjacencyGained, arrived, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura"
    )


@power(
    "m5536a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5536a1(c: Cast) -> None:
    """Watched on the declaration rather than the outcome: the printed line is
    about *making* the attack, so a miss costs the same as a hit. `opportunity`
    rides as a plain attribute, hence the `getattr`."""
    me = c.me

    def swung(ev: AttackDeclared) -> None:
        if ev.target != me or not getattr(ev, "opportunity", False):
            return
        c.damage("1d6", on=ev.attacker)

    c.watch(
        AttackDeclared, swung, until=When.ENCOUNTER, on=me, label=f"{c.ref} spines"
    )


@power(
    "m5536a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m5536a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5536a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m5536a3(c: Cast) -> None:
    """"If both attacks hit" needs both answers at once, and a body that runs
    per target holds nothing between calls -- so the whole power is resolved on
    the first pass over `c.targets`."""
    if not c.first:
        return
    landed = []
    for victim in c.targets:
        c.use_power("m5536a2", on=victim)
        landed.append(c.landed)
    if len(landed) == 2 and all(landed):
        for victim in c.targets:
            c.dazed(until=When.EONT, on=victim)


@power(
    "m5536a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d8", 3, kind=LIMITED),
)
def m5536a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5536a5",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is first bloodied or drops to 0 hit points",
    on=(
        Trigger(Bloodied, about_me, "it is first bloodied"),
        Trigger(Dropped, about_me, "it drops to 0 hit points"),
    ),
)
def m5536a5(c: Cast) -> None:
    """Two printed triggers, so both are declared -- declaring one of them
    looks finished and answers half the sentence. `c.use_power` comes back
    False when the recharge row is spent, which is "if the power is
    available"."""
    if not c.use_power("m5536a4"):
        near = c.within(2, side="enemy")
        if near:
            c.use_power("m5536a2", on=near[0])


# --------------------------------------------------------------------------
# m5748
# --------------------------------------------------------------------------


@power(
    "m5748a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 5, kind=MINION),
)
def m5748a0(c: Cast) -> None:
    """The +1 is part of the attack, so it goes through `c.strike(plus=)` where
    it is read with the roll; the miss damage is a flat 3 the header cannot
    hold -- `half_on_miss` would pay 2."""
    hurt = _is_bloodied(c.world, c.target) if c.target is not None else False
    if c.strike(plus=1 if hurt else 0):
        c.hit()
    else:
        c.flat(3)


@power(
    "m5748a1",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when an ally makes a melee attack against an adjacent enemy",
    on=Trigger(
        AttackDeclared,
        both(by_melee, lambda w, me, ev: ev.attacker != me),
        "an ally attacks an enemy next to it",
    ),
    dropped=("etl.monster.kind_words()",),
)
def m5748a1(c: Cast) -> None:
    """The printed trigger narrows the ally to one creature family, and the
    compendium's kind list does not carry that word -- the blocks it names are
    filed only as reptiles -- so `c.is_kind` on it is false forever, which is
    the silently-false shape. The row answers any ally instead and the
    narrowing is the dropped clause.
    """
    ev = c.trigger
    friend = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if friend is None or victim is None:
        return
    if team(c.world, friend) is not team(c.world, c.me):
        return
    if not c.adjacent(victim):
        return
    c.use_power("m5748a0", on=victim)


# --------------------------------------------------------------------------
# m6028
# --------------------------------------------------------------------------


@power(
    "m6028a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6028a0(c: Cast) -> None:
    """"Power bonus" is the word the card prints in front of "bonus", so that
    is the `kind`: two power bonuses do not add and the larger wins, which is
    what keeps a crowd of these from stacking into nonsense."""
    me = c.me

    def crowded(ctx: dict[str, Any]) -> bool:
        return len([f for f in c.within(1, side="ally") if f != me]) >= 2

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=me, until=When.ENCOUNTER, kind="power", when=crowded)


@power(
    "m6028a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 5, kind=MINION),
)
def m6028a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6039
# --------------------------------------------------------------------------


@power(
    "m6039a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 6),
)
def m6039a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6039a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("3d6", 6, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6039a1(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6039a2",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 6),
    trigger="when an enemy hits it with a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an enemy hits it with a melee attack"),
)
def m6039a2(c: Cast) -> None:
    """The dispatcher aims a single-target enemy row at whoever swung, so the
    riposte needs no target of its own picking."""
    if c.strike():
        c.hit()
        victim = c.target
        c.bonus(
            "attack",
            2,
            on=c.me,
            until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


# --------------------------------------------------------------------------
# m6107
# --------------------------------------------------------------------------


@power(
    "m6107a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 6),
)
def m6107a0(c: Cast) -> None:
    """"Or 1d12 + 12 against a grabbed target" is the same dice and six more,
    so the header keeps the printed line and the extra is laid on top -- which
    is what keeps the damage rescalable."""
    held = c.target is not None and c.target in c.grabbing()
    if c.strike():
        c.hit()
        if held:
            c.flat(6)


@power(
    "m6107a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("", 10, dtype=DamageType.FIRE),
)
def m6107a1(c: Cast) -> None:
    """Flat 10, so the dice half of the header is empty. The grab is refused
    when something is already held, which is the printed condition."""
    if c.strike():
        c.hit()
        if not c.grabbing():
            c.grab()


@power(
    "m6107a2",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is reduced to 0 hit points",
    on=Trigger(Dropped, both(about_me, not_critical),
               "it is reduced to 0 hit points, but not by a critical hit"),
)
def m6107a2(c: Cast) -> None:
    """"But not by a critical hit" is asked now: `Dropped` carries
    `critical` since #428, and `triggers.not_critical` reads it. The row
    fired on any drop before that, including the one its card excludes.
    """

    def scorch() -> None:
        for near in c.within(1, side="any"):
            if near != c.me:
                c.flat(5, dtype=DamageType.FIRE, on=near)

    _clings_on(c, scorch)


# --------------------------------------------------------------------------
# m6475
# --------------------------------------------------------------------------


@power(
    "m6475a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 6, kind=MINION),
)
def m6475a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6569
# --------------------------------------------------------------------------


@power(
    "m6569a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 3, kind=MINION),
)
def m6569a0(c: Cast) -> None:
    """"Until the grab ends" is not a duration the engine has, so the burn is
    held for the encounter and taken off when the grab is let go -- which is a
    `RelationCleared` and not a condition ending."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    burn = c.ongoing(5, on=victim, until=When.ENCOUNTER)
    if burn is None:
        return
    me = c.me

    def freed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.end_effect(burn, why="the grab ended")

    c.watch(
        RelationCleared, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} hold"
    )


@power(
    "m6569a1",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is reduced to 0 hit points",
    on=Trigger(Dropped, both(about_me, not_critical),
               "it is reduced to 0 hit points, but not by a critical hit"),
)
def m6569a1(c: Cast) -> None:
    """"But not by a critical hit" is asked now, off `Dropped.critical`
    (#428). A minion is dead rather than dying, so getting back up is
    `c.reanimate` and not a heal."""
    _clings_on(c)


# --------------------------------------------------------------------------
# m6625
# --------------------------------------------------------------------------


@power(
    "m6625a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 5, kind=MINION),
)
def m6625a0(c: Cast) -> None:
    """"Per ally of its own kind" is by stat block id, not by type word: beast
    and natural are shared by a dozen blocks, and the printed line is about
    this one."""
    if not c.strike():
        return
    c.hit()
    extra = _crowd(c, c.target, "m6625")
    if extra:
        c.flat(extra)


@power(
    "m6625a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("", 6, kind=MINION),
    trigger="when an enemy reduces it to 0 hit points",
    on=Trigger(Dropped, about_me, "an enemy reduces it to 0 hit points"),
)
def m6625a1(c: Cast) -> None:
    """Only the triggering enemy is in the burst, which is a target no `Target`
    can name -- so the row declares none and takes the killer off `Dropped`,
    which carries a `source` for exactly this."""
    killer = getattr(c.trigger, "source", None)
    if killer is None or team(c.world, killer) is team(c.world, c.me):
        return
    if c.distance(killer) > 2:
        return
    if c.attack(c.world.scaling.trim(5, c.level), FORT, on=killer):
        c.flat(6, on=killer)


# --------------------------------------------------------------------------
# m855
# --------------------------------------------------------------------------


@power(
    "m855a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m855a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m855a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m855a1(c: Cast) -> None:
    """The crowd bonus is part of the attack roll, so it goes through
    `c.strike(plus=)`: a `c.bonus` laid first is read by the *next* attack and
    not by this one."""
    victim = c.target
    if victim is None:
        return
    if c.strike(plus=_allies_pressing(c, victim)):
        c.hit()
        c.push(1)


@power(
    "m855a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("actions.legal('ready')",),
)
def m855a2(c: Cast) -> None:
    """The whole trait is a bonus on a *readied* attack, and readying an action
    is not something a creature can do -- so there is no attack for the bonus
    to sit on and no way to recognise one."""


@power(
    "m855a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m855a3(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m855a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m855a4(c: Cast) -> None:
    _trap_shield(c)


# --------------------------------------------------------------------------
# m933
# --------------------------------------------------------------------------


@power(
    "m933a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m933a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m933a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m933a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike(plus=_allies_pressing(c, victim)):
        c.hit()
        c.push(1)


@power(
    "m933a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("actions.legal('ready')",),
)
def m933a2(c: Cast) -> None:
    """The same trait as `m855a2` and the same one absence: nothing readies an
    action, so there is no attack for the bonus to ride."""


@power(
    "m933a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m933a3(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m933a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m933a4(c: Cast) -> None:
    _trap_shield(c)
