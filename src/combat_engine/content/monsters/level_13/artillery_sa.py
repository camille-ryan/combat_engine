"""Monster abilities, level 13: the rest of the artillery.

`artillery.py` holds the six stat blocks that were written first; this file
holds the sixteen that were not, in ref order, and ends with the one minion.
Every number -- hit points, defences, speed, resistances -- loads from
`game.db`. The attack line is the printed total (`Attack(vs=AC, printed=18)`)
and the damage line is header data (`Damage("2d8", 12)`), so the engine takes
the level term back out of the first and can rescale the second.

The conventions of the twelve levels below are kept, and the ones that
actually decided a row here are:

* a stat block printing no range at all means melee 1;
* a printed range band "X/Y" is a normal range and a long one, and `Range`
  holds the first number;
* an area or blast naming "creatures in the burst" takes `EACH_CREATURE`;
  one naming enemies, or naming no target set at all, takes `EACH_ENEMY`;
* `half_on_miss=True` is card data only, so a Miss line is also written as
  `else: c.hit(half=True)`;
* one blow of two damage types keeps the first type in the header and is
  marked `dropped=("Damage(dtypes=)",)`, which is the settled symbol; two
  separately named amounts are a header blow plus a second call and need no
  marker;
* a printed Requirement naming a weapon is left ungated, because a stat
  block carries no gear for anything to ask about.

Eight things this file had to settle.

**A parenthetical total is the trait's arithmetic, not a second number.**
m2715's three attack rows each print a second bonus and a second damage
figure "against a bloodied target", and m2715a3 is the trait that grants
exactly +1 and +2 against bloodied enemies. So the rows carry the base
printed numbers and the trait pays the difference; putting the parenthetical
in the header too would charge it twice. m4126 is the same block with the
trait and without the parentheses.

**"Save ends both" over a vulnerability is one saving throw.** m2715a2
leaves a creature vulnerable *and* slowed on one save. `c.vulnerable` makes
its own save-ends hold, so the slow is given no clock of its own and is
ended from that hold instead -- the shape m195a1 settled one file over.

**Two stages of a failed save are two `escalate` callbacks, chained.**
m5558a1, m5762a3 and m6016a3's burn each print a First and a Second Failed
Saving Throw. `Effect.escalate` is read afresh at every save, so the first
callback replaces the hold with one carrying the next stage -- unlike
`eff.conditions`, which is read once and must never be rewritten.

**An ongoing burn of two types is one burn.** `Effects.apply` takes
`ongoing_types`, so m5762a3's necrotic-and-poison burn ticks once for ten
and takes one save. That is a different thing from a *blow* of two types,
which the header cannot say at all.

**"Recharge when no target is affected" and "when a target saves" are the
same hook.** Both are the hold's own ending, which is what `on_end` is:
m2715a2 and m4126a3 hand their use back from there, the way m3815a1 does.

**A conjuration is already un-attackable.** m3262a2 prints "cannot be
attacked, but it is vulnerable to dispel magic"; `Conjuration` carries no
`Health` by design and `c.dispel` is the second half, so both sentences are
already true of the engine and neither is a gap. The combat advantage its
neighbours give away is laid on the m3262 as `c.gains_advantage` rather than
on each enemy, because that one effect also catches a creature that walks
into the beast's reach later.

**A free action answering a Miss really can reroll it.** m6016a5's effect
reads like an interrupt and is printed as a free action. `resolve.attack`
re-announces the outcome when a reroll in the AFTER window changes it, with
a comment saying so, so the printed action cost is kept.

**"Any living creature" includes the aura's friends.** m6016a0 burns
everybody, which is why it does not use the enemy-only aura helpers; the
owner is still left out, as every aura in the tree leaves its owner out.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn
from combat_engine.content.monsters.level_07.brutes import _living
from combat_engine.content.monsters.level_11.lurkers import _extra_against_the_unready
from combat_engine.content.monsters.level_13.artillery import EVERY_DEFENCE
from combat_engine.content.monsters.level_13.soldiers import _burn_and_hold
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Defences,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Powers,
    Ranged,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import neighbours
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, scenery, squares, team
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me

#: The three kinds of movement somebody else makes happen. "Willingly moves"
#: is every other kind, which is what `Forced` spells its steps with.
FORCED_STEPS = ("push", "pull", "slide")


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _against_the_bloodied(c: Cast) -> None:
    """"+1 bonus to attack rolls and a +2 bonus to damage rolls against
    bloodied enemies."

    Neither sentence prints a type word, so both are untyped, and they are
    two calls because one is read off the attack and one off the damage.
    Both contexts carry `target`, which is who the printed line is about --
    `attacker` would be the m2715 itself.
    """
    me = c.me

    def at_a_bloodied_one(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.bloodied(on=victim)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=at_a_bloodied_one)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=at_a_bloodied_one)


def _all_defences(c: Cast, value: int, *, until: When, when: Any = None) -> list[Effect]:
    """"A +2 bonus to all defenses" is four numbers, because the engine holds
    each defence separately and a modifier named "all defenses" would be a
    bonus to nothing."""
    laid = [
        c.bonus(defended, value, on=c.me, until=until, when=when)
        for defended in EVERY_DEFENCE
    ]
    return [eff for eff in laid if eff is not None]


def _softened_defences(c: Cast, victim: int, hold: Effect) -> None:
    """"-2 penalty to all defenses" riding on somebody else's saving throw.

    Four penalties with no clock of their own, ended from the hold that
    carries the printed save -- which is what "save ends both" means and
    what giving each of them `When.SAVE_ENDS` would get wrong four times
    over.
    """
    for defended in EVERY_DEFENCE:
        taken = c.penalty(defended, 2, on=victim, until=When.ENCOUNTER)
        if taken is not None:
            hold.on_end.append(
                lambda eff=taken: c.world.effects.end(eff, "the hold is over")
            )


def _lifts_somebody(c: Cast, radius: int, squares_: int) -> None:
    """"The creature or an ally within range can fly up to N squares."

    The fly speed is lent for the length of the move and taken straight back:
    `movement.mode_of` puts anything carrying the mode into the air the
    moment it moves, so a lent speed left behind would keep it there. The
    shape m225a3 settled.
    """
    me = c.me
    mates = sorted(
        friend
        for friend in c.within(radius, side="ally")
        if friend != me and alive(c.world, friend)
    )
    flier = me
    if mates and not c.may("fly itself", who=me):
        flier = c.choose(mates, f"{c.ref}: which ally it lifts") or me
    lent = c.mode("fly", squares_, until=When.EOT, on=flier)
    try:
        c.move(squares_, who=flier)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it comes down")


def _no_limited_attacks(c: Cast, victim: int, hold: Effect) -> None:
    """"The target cannot use daily or encounter powers (save ends)."

    There is no switch for a whole usage class, so the victim's rows are
    walked and each one that prints an attack line and is not at-will is
    taken away by name. Every hold is ended by the *one* save-ends hold that
    also carries the burn, because the card prints one saving throw.
    """
    known = c.world.get(victim, Powers)
    if known is None:
        return
    for ref in known.all:
        p = get(ref)
        if p is None or p.usage is Usage.AT_WILL or p.attack is None:
            continue
        taken = c.forbid(ref, on=victim, until=When.ENCOUNTER)
        if taken is not None:
            hold.on_end.append(
                lambda eff=taken: c.world.effects.end(eff, "the silence lifts")
            )


def _two_basics(c: Cast) -> None:
    """"Effect: it makes two basic attacks." Each swing picks its own target,
    which is what a row printing no target of its own leaves open -- and
    `c.basic` with no `on=` would aim at `c.target`, which is None here."""
    for _ in range(2):
        foes = sorted(
            foe
            for foe in c.enemies()
            if alive(c.world, foe) and c.distance(foe) <= c.reach()
        )
        if not foes:
            return
        c.basic(on=foes[0])


def _vulnerable_to(c: Cast, who: int, dtype: DamageType) -> bool:
    """Is that creature taking extra from this type? `c.resistances` answers
    the other half of `Defences` and there is no reader for this one."""
    defences = c.world.get(who, Defences)
    return bool(defences is not None and defences.vulnerable.get(dtype, 0) > 0)


def _nearest_mate(c: Cast, who: int) -> int | None:
    """"Its nearest ally" -- asked of the victim's side, not of the caster's.
    `c.within(side="ally")` means an ally *of the caster*, so the pool here
    is the caster's enemies with the victim itself taken out."""
    mates = [
        foe for foe in c.enemies() if foe != who and alive(c.world, foe)
    ]
    if not mates:
        return None
    return min(mates, key=lambda f: (distance_between(c.world, who, f), f))


def _in_the_area(c: Cast, victim: int, radius: int, side: str) -> list[int]:
    """Who stands in this area, for an Effect line that reaches wider than
    the row's own target. The burst is measured from the squares the power
    covered where it has them, and from the one creature it named where the
    header declared a single target and left `c.area()` empty."""
    area = c.area()
    if area:
        return sorted(c.in_squares(area, side=side))
    return sorted(c.within(radius, of=victim, side=side))


# ==========================================================================
# m115752
# ==========================================================================


@power(
    "m115752a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 12),
)
def m115752a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115752a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 12),
)
def m115752a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115752a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("3d8", 20, kind=LIMITED),
)
def m115752a2(c: Cast) -> None:
    """The push is measured before the fall, which is the order the card
    prints and the only order that moves anybody: a prone creature cannot be
    pushed out of its square by this row's arithmetic any differently, but
    the sentence reads as one shove and then the ground."""
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


# ==========================================================================
# m115828
# ==========================================================================


@power(
    "m115828a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 9),
)
def m115828a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115828a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 12),
)
def m115828a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115828a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 9),
)
def m115828a2(c: Cast) -> None:
    """An area burst is aimed at a square rather than centred on the
    creature firing it, so "creatures in the burst" is `EACH_CREATURE`
    without catching the m115828 in its own blast."""
    if c.strike():
        c.hit()


# ==========================================================================
# m1911
# ==========================================================================


@power(
    "m1911a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m1911a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1911a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("1d10", 7, dtype=DamageType.NECROTIC),
)
def m1911a1(c: Cast) -> None:
    """"Until the end of the m1911's next turn" is the source's clock, which
    is what `When.EONT` measures."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m1911a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m1911a2(c: Cast) -> None:
    """The healing is not part of the attack: it pays out whether anybody was
    hit or not, so it is guarded by `c.first` rather than hung on the hit --
    and it reaches *allies*, which leaves the m1911 itself out as every
    printed line of that shape does."""
    if c.first:
        for friend in _in_the_area(c, c.me, 2, "ally"):
            if c.is_kind("undead", on=friend):
                c.heal(5, on=friend)
    if c.strike():
        c.hit()


# ==========================================================================
# m2517
# ==========================================================================


@power(
    "m2517a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 4),
)
def m2517a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2517a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 8),
)
def m2517a1(c: Cast) -> None:
    """20/40 is a normal range and a long one, and `Range` holds one
    number."""
    if c.strike():
        c.hit()


@power(
    "m2517a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 8, kind=LIMITED),
)
def m2517a2(c: Cast) -> None:
    """The printed Requirement names the weapon m2517a1 is already shooting
    with, and a stat block carries no gear for anything to ask about, so the
    row is left usable rather than gated on something nothing can answer."""
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2517a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2517a3(c: Cast) -> None:
    """The printed recharge sentence sits on top of the die the database
    files, and the two only ever agree to make the row available sooner. It
    is armed once for the whole use, not once per enemy."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(2)


# ==========================================================================
# m2651
# ==========================================================================


@power(
    "m2651a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 2),
)
def m2651a0(c: Cast) -> None:
    """Two separately named amounts of two types are two packets: the header
    holds the untyped blow and the die of psychic is rolled beside it."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.PSYCHIC)


@power(
    "m2651a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m2651a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2651a2",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2651a2(c: Cast) -> None:
    """Declared with no target because the two halves aim at different
    creatures and which one happens is the m2651's choice. The printed Effect
    spells the creature's id twice and garbles it once; the creature every
    reading of the sentence means is this one."""
    _lifts_somebody(c, 10, 5)


@power(
    "m2651a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m2651a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2651a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2651a4(c: Cast) -> None:
    """Two printed "save ends" clauses on one sentence are one hold: the burn
    carries the saving throw and the silence is ended from it, so the victim
    rolls once and both halves go together."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = _burn_and_hold(c, victim, 5, DamageType.PSYCHIC)
    _no_limited_attacks(c, victim, hold)


# ==========================================================================
# m2715
# ==========================================================================


@power(
    "m2715a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 4),
)
def m2715a0(c: Cast) -> None:
    """The parenthetical totals against a bloodied target are m2715a3's
    arithmetic already done on the card; the header carries the base numbers
    so the trait is not paid twice."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.COLD)
        c.slide(1)


@power(
    "m2715a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("2d6", 6, dtype=DamageType.COLD),
)
def m2715a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2715a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m2715a2(c: Cast) -> None:
    """"Save ends both" over a vulnerability and a condition.

    `c.vulnerable` holds the saving throw, because it is the target's own
    hold; the slow is given `When.ENCOUNTER` so it has no second clock and
    is ended from the vulnerability instead. "Recharges when no target is
    affected by this power" is that same ending, which is what `on_end` is.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    weakness = c.vulnerable(5, DamageType.COLD, on=victim, until=When.SAVE_ENDS)
    if weakness is None:
        return
    chilled = c.slowed(on=victim, until=When.ENCOUNTER)
    if chilled is not None:
        weakness.on_end.append(lambda: c.world.effects.end(chilled, "it thaws"))
    weakness.on_end.append(lambda: c.restore_use(c.ref, on=me))


@power(
    "m2715a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2715a3(c: Cast) -> None:
    """Filed as a standard at-will and plainly a trait: it costs no action,
    names no target and is a standing modifier."""
    _against_the_bloodied(c)


# ==========================================================================
# m3262
# ==========================================================================


@power(
    "m3262a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 3),
)
def m3262a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3262a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 3),
)
def m3262a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3262a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def m3262a2(c: Cast) -> None:
    """It puts something on the board beside somebody and the opening follows
    the thing about.

    The square is beside an enemy in range, which is what the card names, so
    it is picked rather than left to the free-square search.

    The opening is laid on the m3262 as `c.gains_advantage` rather than on
    each enemy as `c.grants_advantage`: one effect, asked at the moment a
    swing is rolled, so a creature that walks into the conjuration's reach
    afterwards gives the same opening away -- which the printed line says and
    a snapshot of today's enemies would not.

    "Cannot be attacked" and "vulnerable to dispel magic" are both already
    true: a `Conjuration` carries no `Health` by design and `c.dispel` is the
    other half. `speed=5` is the move action the card prints.
    """
    me = c.me
    reachable = sorted(
        foe for foe in c.enemies() if alive(c.world, foe) and c.distance(foe) <= 10
    )
    if not reachable:
        return
    beside = reachable[0]
    spots = sorted(
        {
            step
            for occupied in squares(c.world, beside)
            for step in neighbours(occupied)
            if not c.in_squares({step})
        }
    )
    where = c.choose(spots, f"{c.ref}: where it stands") if spots else None
    beast = c.conjure(at=where, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)
    if not beast:
        return

    def beside_it(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.adjacent_to(beast, victim)

    c.gains_advantage(beside_it, until=When.ENCOUNTER, on=me)


@power(
    "m3262a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m3262a3(c: Cast) -> None:
    """The printed Requirement names the weapon m3262a1 is already shooting
    with; a stat block carries no gear, so the row is left ungated."""
    if c.strike():
        c.hit()


@power(
    "m3262a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3262a4(c: Cast) -> None:
    """Filed as a standard at-will and plainly a trait. Whether the blow had
    the opening is read off the `Hit`: a one-shot grant has already been
    spent by the time a second asking could be made. The printed line names
    melee and ranged, so the rider is narrowed to those two."""
    _extra_against_the_unready(c, "1d6", ("melee", "ranged"))


@power(
    "m3262a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3262a5(c: Cast) -> None:
    """Who has hurt it lately is asked as the next attack rolls, not now:
    "since the m3262's last turn" is a window that is still open while the
    bonus stands, and a list taken here would be stale the moment anybody
    else swung -- and empty on the turn a monster usually spends a minor
    action. Both halves are `once=True`, because the card pays for one
    attack, and only the first prints a type word."""
    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    c.bonus("attack", 1, on=me, kind="power", until=When.ENCOUNTER, once=True,
            when=paid_back)
    c.bonus("damage", 3, on=me, until=When.ENCOUNTER, once=True, when=paid_back)


# ==========================================================================
# m3937
# ==========================================================================


@power(
    "m3937a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 6),
)
def m3937a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3937a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8),
)
def m3937a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3937a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m3937a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3937a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3937a3(c: Cast) -> None:
    """A plain "+2 bonus" with no type word is untyped, and "all defenses" is
    four numbers. `c.total_defence` is the wrong tool: it runs to the start of
    the next turn and the card prints the end of it."""
    c.heal(10, on=c.me)
    _all_defences(c, 2, until=When.EONT)


# ==========================================================================
# m4126
# ==========================================================================


@power(
    "m4126a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m4126a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4126a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 6),
    dropped=("c.retrieve()",),
)
def m4126a1(c: Cast) -> None:
    """3/6 is a normal range and a long one. The printed Effect names a row
    belonging to another stat block and is plainly about this one; having to
    pick the thrown weapon up again is the dropped half, because a stat block
    carries no gear, nothing lands on the ground and `c.forbid` would need a
    duration the card does not print."""
    if c.strike():
        c.hit()


@power(
    "m4126a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 4),
    dropped=("Power.reach_alt",),
)
def m4126a2(c: Cast) -> None:
    """Two numbers for water and two for dry land. The damage half is
    written out, because `c.terrain` is exactly the question the parenthesis
    asks; the longer range has nowhere to go -- a header carries one reach
    and the alternative band it does carry is for a melee-or-ranged row."""
    if not c.strike():
        return
    if c.terrain("aquatic"):
        c.damage("3d6", 6)
    else:
        c.hit()


@power(
    "m4126a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("3d8", 4, kind=LIMITED),
)
def m4126a3(c: Cast) -> None:
    """One saving throw carries the burn and four penalties, and the printed
    recharge is that hold's own ending -- which is what "recharges when a
    target saves against this effect" measures."""
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = _burn_and_hold(c, victim, 5, DamageType.UNTYPED)
    _softened_defences(c, victim, hold)
    hold.on_end.append(lambda: c.restore_use(c.ref, on=me))


@power(
    "m4126a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4126a4(c: Cast) -> None:
    """Filed as a standard at-will and plainly a trait."""
    _against_the_bloodied(c)


# ==========================================================================
# m5374
# ==========================================================================
#
# Elite, and it prints no row that acts twice, so it takes no second
# initiative count: an elite is two creatures' worth of hit points and
# experience before it is anything else.


@power(
    "m5374a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5374a0(c: Cast) -> None:
    """"Against any creature marking it" is asked of the swing rather than
    held as a flat number: the defence context carries `attacker`, and
    `c.marked` with `by=` is the relation read from the other side. A plain
    "+2 bonus" prints no type word and is untyped."""
    me = c.me

    def by_my_marker(ctx: dict[str, Any]) -> bool:
        shooter = ctx.get("attacker")
        return shooter is not None and c.marked(on=me, by=shooter)

    _all_defences(c, 2, until=When.ENCOUNTER, when=by_my_marker)


@power(
    "m5374a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d6", 4),
)
def m5374a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5374a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("3d10", 6, dtype=DamageType.PSYCHIC),
)
def m5374a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5374a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m5374a3(c: Cast) -> None:
    """One creature is attacked and the whole burst feels the Effect.

    No damage on the hit line, so there is no `damage=` and `c.hit` is never
    called -- the burn is the whole of it. The spread is hung on the burn's
    *own* ticks, matched by effect id rather than by damage type, so other
    psychic damage landing on the same creature does not pay it out.

    The Effect lines run whether the attack hit or not, which is what an
    Effect is; the printed recharge is a critical with m5374a4 and is armed
    from here, because a recharge row cannot be spent before its first use.
    """
    me, victim = c.me, c.target
    if victim is None:
        return

    def crit_with_the_minor(ev: Hit) -> None:
        if ev.attacker == me and ev.critical and ev.power == "m5374a4":
            c.restore_use(c.ref, on=me)

    c.watch(Hit, crit_with_the_minor, until=When.ENCOUNTER, on=me, label=f"{c.ref} back")

    for foe in _in_the_area(c, victim, 2, "enemy"):
        c.grants_advantage(on=foe, until=When.EONT)
    for friend in _in_the_area(c, victim, 2, "ally"):
        if friend == me:
            continue
        if c.choose(["shift", "move"], f"{c.ref}: how it gets clear") == "shift":
            c.shift(1, who=friend)
        else:
            c.move(max(1, c.speed_of(friend) // 2), who=friend)

    if not c.strike():
        return
    burn = c.ongoing(20, DamageType.PSYCHIC, on=victim)
    if burn is None:
        return
    tag = f"e{burn.id}["

    def spreads(ev: DamageApplied) -> None:
        if ev.target != victim or ev.amount <= 0 or not ev.detail.startswith(tag):
            return
        for mate in sorted(
            foe
            for foe in c.enemies()
            if foe != victim
            and alive(c.world, foe)
            and distance_between(c.world, victim, foe) <= 3
        ):
            c.flat(5, dtype=DamageType.PSYCHIC, on=mate)

    rider = c.watch(
        DamageApplied, spreads, until=When.ENCOUNTER, on=me, label=f"{c.ref} spread"
    )
    burn.on_end.append(lambda: c.world.effects.end(rider, "the screaming stops"))


@power(
    "m5374a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(20),
    target=Target(
        "enemy", 1,
        label="one dazed creature",
        conditions=frozenset({Condition.DAZED}),
    ),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("1d10", 6, dtype=DamageType.PSYCHIC),
)
def m5374a4(c: Cast) -> None:
    """"One dazed creature" is the target line now, so the redirect came out.

    Ongoing psychic does not stack -- the highest applies -- so "if the
    target is already taking ongoing psychic damage, the ongoing damage
    increases by 5" is one hold to find and one number to raise, not a
    second burn beside the first.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    standing = max(
        (
            eff.ongoing[0]
            for eff in c.world.effects.of(victim)
            if eff.ongoing is not None and eff.ongoing[1] is DamageType.PSYCHIC
        ),
        default=0,
    )
    amount = standing + 5 if standing else 10
    _burn_and_hold(
        c, victim, amount, DamageType.PSYCHIC, conditions=(Condition.DAZED,)
    )


@power(
    "m5374a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(20),
    target=NO_TARGET,
)
def m5374a5(c: Cast) -> None:
    """It spends somebody else's turn for them.

    `c.basic(who=)` names who swings and `on=` names who is hit, and the two
    are easy to conflate -- a grant written without `on=` on a row whose own
    target is None attacks nobody at all. The enemy is the m5374's choice,
    which is what the card says.

    The quarry is chosen before the move, so `c.run_at` can walk the helper
    into reach of it; `c.move` hands its destinations to the decider
    unordered and the ally was as likely to walk away from the creature it
    was about to swing at. The swing is then gated on the helper's own reach,
    because "moves its speed" may not be enough to close the gap and an
    explicit target is never reach-checked downstream. The daze is not
    gated -- it is the price of being driven, printed as its own sentence.
    """
    me = c.me
    mates = sorted(
        friend
        for friend in c.within(20, side="ally")
        if friend != me and alive(c.world, friend)
    )
    helper = c.choose(mates, f"{c.ref}: which ally it drives") if mates else None
    if helper is None:
        return
    quarry = sorted(foe for foe in c.enemies() if alive(c.world, foe))
    picked = c.choose(quarry, f"{c.ref}: who the ally swings at") if quarry else None
    if picked is not None:
        c.run_at(picked, who=helper)
        if distance_between(c.world, helper, picked) <= _swing_reach(c, helper):
            c.basic(who=helper, on=picked)
    c.dazed(on=helper, until=When.EONT)
    _recharge_when_bloodied(c)


# ==========================================================================
# m5558
# ==========================================================================


@power(
    "m5558a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5),
)
def m5558a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5558a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d8", 2, dtype=DamageType.PSYCHIC),
)
def m5558a1(c: Cast) -> None:
    """Two stages of failure, chained through `escalate`.

    `Effect.escalate` is read afresh at every saving throw, so the first
    callback can hand the hold its own successor -- which is why this is
    written here and not as a rewrite of `eff.conditions`, a field read once
    on the way in and once on the way out and never between.

    "Its nearest ally" is asked of the victim's side: `side="ally"` would
    mean an ally of the m5558.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def second(eff: Effect) -> None:
        c.world.effects.end(eff, "it gave in")
        c.condition(
            Condition.DOMINATED,
            until=When.SAVE_ENDS,
            on=victim,
            ongoing=(10, DamageType.PSYCHIC),
        )

    def first(eff: Effect) -> None:
        mate = _nearest_mate(c, victim)
        if mate is not None:
            c.basic(who=victim, on=mate)
        eff.escalate = second

    c.condition(
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(10, DamageType.PSYCHIC),
        escalate=first,
    )


# ==========================================================================
# m5762
# ==========================================================================


@power(
    "m5762a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5762a0(c: Cast) -> None:
    """Deliberately inert, and complete.

    Every clause is about a creature that is already dead: what state its
    body is left in, that it cannot be raised while it stays that way, and
    the two ways the state is undone -- a touch, or blood spilled on it.
    Nothing there changes a fight: a slain creature is out of the fight by
    being slain, `Condition.PETRIFIED` laid on a corpse is read by nothing,
    and raising the dead happens between encounters.
    """


@power(
    "m5762a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 10, dtype=DamageType.NECROTIC),
)
def m5762a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5762a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 12),
)
def m5762a2(c: Cast) -> None:
    """The bonus is against *that* creature, not a flat +4 to everything,
    which is a much heavier card than the one printed. The card prints the
    type word, so it is a power bonus -- and `stacks=False` is not also
    needed, because two bonuses of one kind already do not add: the larger
    wins, so a second shot at the same creature renews rather than doubles.
    `c.bonus` refuses the pair, since `stacks=False` buckets under the row's
    own ref instead of under the printed type."""
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def at_that_one(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    c.bonus("damage", 4, on=me, kind="power", until=When.EONT, when=at_that_one)


@power(
    "m5762a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 12, kind=LIMITED),
)
def m5762a3(c: Cast) -> None:
    """A burn of two types at once is one burn, which `ongoing_types` says:
    ten points a turn that are both necrotic and poison, on one saving
    throw, rather than two holds ticking for twenty.

    Each stage replaces the hold before it, because the second printed line
    says the power's other effects end.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burns = (DamageType.NECROTIC, DamageType.POISON)

    def second(eff: Effect) -> None:
        c.world.effects.end(eff, "the venom finishes its work")
        c.unconscious(on=victim, until=When.SAVE_ENDS)

    def first(eff: Effect) -> None:
        c.world.effects.end(eff, "it spreads")
        c.world.effects.apply(
            victim, me, When.SAVE_ENDS, label=c.ref,
            conditions=(Condition.IMMOBILIZED,),
            ongoing=(10, DamageType.NECROTIC), ongoing_types=burns,
            escalate=second,
        )

    c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=c.ref,
        ongoing=(10, DamageType.NECROTIC), ongoing_types=burns,
        escalate=first,
    )


_M5762_SWUNG = "an adjacent enemy attacks it with a melee attack"


@power(
    "m5762a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION],
    trigger=_M5762_SWUNG,
    on=Trigger(AttackDeclared, both(targets_me, by_melee), _M5762_SWUNG),
)
def m5762a4(c: Cast) -> None:
    """No attack roll and no header damage: five points and a step away are
    the whole of it, so the damage is flat.

    "The triggering enemy" is read off `PowerUsed.trigger`'s event rather
    than off `c.target`: an immediate action declares a target and is then
    aimed at whoever the trigger named. The adjacency is asked here because
    `targets_me` is the half a ready-made predicate says.
    """
    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is None or not c.adjacent(foe):
        return
    c.flat(5, dtype=DamageType.NECROTIC, on=foe)
    c.teleport(5, who=c.me)


# ==========================================================================
# m6016
# ==========================================================================
#
# Elite, and it prints no row that acts twice, so it takes no second
# initiative count.


@power(
    "m6016a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6016a0(c: Cast) -> None:
    """"Any living creature", so its own side burns too -- which is why the
    enemy-only aura helpers are not used here. The owner is still left out,
    as every aura in the tree leaves its owner out, and membership is asked
    at the moment the turn ends because that is the question the printed
    sentence asks."""
    me, label = c.me, c.ref
    c.aura(1, label=label, until=When.ENCOUNTER)

    def ending(ev: TurnEnd) -> None:
        who = ev.actor
        if getattr(ev, "ghost", False) or who == me or not _living(c, who):
            return
        if c.in_my_aura(who, label=label):
            c.flat(10, dtype=DamageType.NECROTIC, on=who)

    c.watch(TurnEnd, ending, until=When.ENCOUNTER, on=me, label=f"{label} ring")


@power(
    "m6016a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m6016a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


@power(
    "m6016a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("4d8", 3, dtype=DamageType.NECROTIC),
    dropped=("c.cannot_approach()",),
)
def m6016a2(c: Cast) -> None:
    """The damage is exact. "Cannot willingly move closer to the m6016" is
    the dropped half: `c.cannot_shift`, `c.no_walk` and `c.immobilized` all
    stop movement outright and none of them can be pointed at a direction."""
    if c.strike():
        c.hit()


@power(
    "m6016a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(
        vs=REF, printed=18
    ),
    damage=Damage(
        "4d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True
    ),
    dropped=("c.kill()",),
)
def m6016a3(c: Cast) -> None:
    """Both outcomes leave a burn, and only on a creature that already takes
    extra from necrotic -- which `Defences.vulnerable` holds and nothing
    reads, so it is read here. The burn is printed untyped.

    "Second Failed Saving Throw: the target dies" is the dropped half. A
    creature is put down by damage, and a blow large enough to be sure of it
    is a different sentence that resistance and temporary hit points would
    both read.
    """
    victim = c.target
    if victim is None:
        return
    landed = bool(c.strike())
    if landed:
        c.hit()
    else:
        c.hit(half=True)
    if _vulnerable_to(c, victim, DamageType.NECROTIC):
        c.ongoing(20 if landed else 10, on=victim)


@power(
    "m6016a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("4d6", 4, dtype=DamageType.COLD, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m6016a4(c: Cast) -> None:
    """"If at least one creature takes damage" pays once for the whole use,
    and the body runs once per target -- so the fact that it has been paid is
    recorded as a hold on the m6016 rather than kept in a local nothing else
    can see."""
    fed = f"{c.ref} fed"
    if not c.strike():
        return
    if c.hit() <= 0:
        return
    if any(eff.label == fed for eff in c.world.effects.of(c.me)):
        return
    c.effect(fed, on=c.me, until=When.EOT)
    c.temp_hp(25, on=c.me)


_M6016_MISSED = "the m6016 misses an enemy with an attack"


def _i_missed_an_enemy(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    victim = getattr(ev, "target", None)
    return victim is not None and team(world, victim) is not team(world, me)


@power(
    "m6016a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6016_MISSED,
    on=Trigger(Miss, _i_missed_an_enemy, _M6016_MISSED),
)
def m6016a5(c: Cast) -> None:
    """A free action that rerolls the miss it is answering.

    That really works: `resolve.attack` re-announces the outcome when a
    reroll in the AFTER window turns a miss into a hit, with a comment
    saying why, so the printed action cost is kept rather than promoted to an
    interrupt. The damage goes out first, because the card prints it first
    and it is paid whether the second roll lands or not.

    Both the printed recharge sentences are armed from here, which is all
    that is needed: a recharge row cannot be spent before its first use. The
    25 hit points are lost rather than suffered, and untyped damage to itself
    is the closest the engine has -- it reads the m6016's own resistances,
    which are necrotic only, so nothing is shrugged off.
    """
    me = c.me
    for foe in sorted(
        foe for foe in c.within(3, side="enemy") if foe != me and alive(c.world, foe)
    ):
        c.flat(15, dtype=DamageType.NECROTIC, on=foe)
    c.reroll_attack()
    _recharge_when_bloodied(c)

    def bleeds_for_it(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or not alive(c.world, me):
            return
        if c.ref not in c.expended(on=me):
            return
        if c.may("lose 25 hit points to ready it again", who=me):
            c.flat(25, on=me)
            c.restore_use(c.ref, on=me)

    c.watch(
        TurnStart, bleeds_for_it, until=When.ENCOUNTER, on=me, label=f"{c.ref} price"
    )


# ==========================================================================
# m6057
# ==========================================================================


@power(
    "m6057a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5),
)
def m6057a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6057a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 5),
)
def m6057a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6057a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("3d10", 10, kind=LIMITED),
)
def m6057a2(c: Cast) -> None:
    """"Willingly" is the whole of the clause: a push, a pull and a slide are
    the three steps somebody else makes happen, and `Moved.kind_` is spelled
    with the same word `Forced` uses, so they are the three to leave out.
    `Moved` rather than `MoveEnd`, because the rider is about the fact of
    moving and not about where the creature finished."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def stirred(ev: Moved) -> None:
        if ev.actor == victim and getattr(ev, "kind_", "") not in FORCED_STEPS:
            c.damage("1d10", on=victim)

    c.watch(
        Moved, stirred, until=When.SONT, on=c.me, once=True, label=f"{c.ref} twinge"
    )


_M6057_BLED = "it is first bloodied"


@power(
    "m6057a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6057_BLED,
    on=Trigger(Bloodied, about_me, _M6057_BLED),
)
def m6057a3(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else."""
    c.temp_hp(10, on=c.me)


_M6057_STRUCK = "it hits an enemy with an attack"


def _i_hit_an_enemy(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    victim = getattr(ev, "target", None)
    return victim is not None and team(world, victim) is not team(world, me)


@power(
    "m6057a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6057_STRUCK,
    on=Trigger(Hit, _i_hit_an_enemy, _M6057_STRUCK),
)
def m6057a4(c: Cast) -> None:
    """The extra die is dealt to whoever the trigger named, not to `c.target`
    -- the row declares itself on the m6057 and the blow landed somewhere
    else. It arrives alongside the attack's own damage rather than after it,
    which is the same blow either way."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("1d10", on=victim)


# ==========================================================================
# m6120
# ==========================================================================
#
# Elite, and it prints no row that acts twice, so it takes no second
# initiative count.


@power(
    "m6120a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6120a0(c: Cast) -> None:
    """Regeneration with an exception, which `c.regeneration` has no hook
    for: one flag, set by necrotic damage and cleared by the very turn it
    skips. "Has at least 1 hit point" is the printed floor and is asked each
    turn, because a creature at 0 does not heal its way back up."""
    me = c.me
    skip = {"on": False}

    def seared(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.NECROTIC in ev.types():
            skip["on"] = True

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if skip["on"]:
            skip["on"] = False
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.heal(5, on=me)

    c.watch(DamageApplied, seared, until=When.ENCOUNTER, on=me, label=f"{c.ref} burned")
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} regen")


@power(
    "m6120a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 10),
)
def m6120a1(c: Cast) -> None:
    """"Until the start of its next turn" is the target's clock, not the
    m6120's, which is what `When.SOTNT` measures."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SOTNT)


@power(
    "m6120a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d6", 4),
)
def m6120a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m6120a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6120a3(c: Cast) -> None:
    """Declared with no target: the two swings pick their own, which is what
    a row printing no target line leaves open."""
    _two_basics(c)


@power(
    "m6120a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("2d10", 11, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6120a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(until=When.SAVE_ENDS)


_M6120_FELLED = "it drops to 0 hit points"


@power(
    "m6120a5",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6120_FELLED,
    on=Trigger(Dropped, about_me, _M6120_FELLED),
)
def m6120a5(c: Cast) -> None:
    """Off the board and then back on it whole.

    The return is paid by `c.reanimate` and not by `c.heal`: the creature is
    already down, and a heal cannot give a corpse a square again. The hit
    points it comes back with are its printed maximum, which is a column, so
    they are read rather than written.

    "All effects on her end" is run before the removal, so the removal is not
    one of the effects it ends. The relocation waits for the turn the card
    waits for.
    """
    me = c.me
    health = c.world.get(me, Health)
    whole = health.max_hp if health is not None else 1
    for eff in list(c.world.effects.of(me)):
        c.world.effects.end(eff, "she is gone")
    c.condition(Condition.REMOVED, until=When.SONT, on=me)

    def returns(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if not alive(c.world, me):
            c.reanimate(on=me, hp=whole, until=When.ENCOUNTER)
        else:
            c.heal(whole, on=me)
        c.teleport(5, who=me)
        c.restore_use("m6120a4", on=me)

    c.watch(TurnStart, returns, until=When.SONT, on=me, once=True, label=c.ref)


# ==========================================================================
# m6143
# ==========================================================================


@power(
    "m6143a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 10),
)
def m6143a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6143a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 10),
)
def m6143a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6143a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d8", 10, kind=LIMITED),
)
def m6143a2(c: Cast) -> None:
    """Whatever it threw is rolled for, and three of the six faces do
    something.

    "Falls prone and cannot stand" is `c.prone(held=)`: prone pinned for as
    long as the saving throw lasts, rather than two clocks on one sentence.
    The clinging half of that face is a watch rather than a standing
    vulnerability, because the printed line adds a burn on top of the fire
    rather than making the fire bigger -- and `c.ongoing` enforces the
    highest-only rule if the creature is already burning.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    face = c.roll("1d6")
    if face in (3, 4):
        c.slowed(on=victim, until=When.SAVE_ENDS)
    elif face == 5:
        c.blinded(on=victim, until=When.SAVE_ENDS)
    elif face == 6:
        c.prone(on=victim, held=When.SAVE_ENDS)

        def clings(ev: DamageApplied) -> None:
            if ev.target == victim and ev.amount > 0 and DamageType.FIRE in ev.types():
                c.ongoing(5, DamageType.FIRE, on=victim)

        c.watch(
            DamageApplied, clings, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} slick"
        )


def _by_a_hearth(world: World, eid: int) -> bool:
    """"Must be adjacent to a fireplace or hearth" -- a fire on the map, which
    is what `query.scenery` reads. The module-level function is the one a
    `requires=` gate can call, and `of=` is not optional: without an origin
    the `within` guard skips every candidate silently."""
    return bool(scenery(world, "fire", within=1, of=eid))


@power(
    "m6143a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d10", 10, dtype=DamageType.FIRE, kind=LIMITED),
    requires=_by_a_hearth,
    requires_text="the m6143 must be adjacent to a fireplace or hearth",
)
def m6143a3(c: Cast) -> None:
    """A Requirement on a standard action is safe where the same gate on a
    trait would not be: `turns.arm_traits_of` arms a trait once, so a
    Requirement that starts false kills it for the fight. This row is offered
    turn by turn and asked afresh each time.

    A blast is not centred on the creature firing it, so `EACH_CREATURE` does
    not catch the m6143 in its own line of fire.
    """
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


# ==========================================================================
# The minion. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


@power(
    "m6187a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=10, kind=MINION),
)
def m6187a0(c: Cast) -> None:
    """Melee 10 as printed, which is a reach and not a range: it provokes,
    it is stopped by a grab, and it is not a ranged attack. Other blocks in
    the tree print the same thing."""
    if c.strike():
        c.hit()
