"""Monster abilities, level 11: the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. A
minion's damage is the flat number the card prints, `Damage(bonus=n,
kind=MINION)`, so an MM1 block can be rescaled later, and its single hit
point is a column like every other number.

The conventions of the ten minion sweeps below are kept: a card printing no
range at all is melee 1, a printed "10/20" band takes the normal range, a
**trait** costs no action and has no target and arms the watches that hold
it for the rest of the fight, "another of its kind" counts by `Ident.ref`
because every creature in a fight may share a type word, and a blow printing
two numbers keeps the base in the header where a rescale can find it and
adds the difference with `c.flat`.

Five things this file had to settle.

**Six death throes, three of them with the trigger in the wrong column.**
m4037a1, m4039a1, m4040a1 and m5999a2 print "when reduced to 0 hit points"
as a free action with an encounter limit. m1881a1, m2604a1 and m3803a1 print
the same sentence where a keyword belongs and are handed over as standard
at-wills. All of them are written the first way, which is what the sentence
means, and `Trigger(Dropped, about_me, ...)` is the half the engine reads.

**A parenthetical that is the creature's own trait showing through is
written once.** m2716 prints "+18 vs AC (+19 against a bloodied target)" and
"7 damage (10 damage to a bloodied target)" on both its attacks, and then
prints a trait granting +1 to attack rolls and +2 to damage rolls against
bloodied enemies. The headers carry the plain printed numbers and the trait
carries the bonuses; writing the parentheticals out as well would pay twice.
The card's 10 is one more than 7 plus the trait, which is the card's
arithmetic and not a second rule.

**An alternative bonus is two gates, not two bonuses.** m1625a1's +1 and +3
replace each other, and two untyped bonuses laid together would add. Each is
gated so that exactly one can ever be true.

**A grab the engine never breaks needs nothing said about its range.**
m2082a0 keeps its victim while it stays within 2 squares, which loosens the
ordinary rule -- and `Relation.GRABBED_BY` is cleared by an escape and by
nothing else, so no distance would have broken it at one square either.
"Only one target at a time" is the half with teeth and is written.

**Two briefs print a proper name through the extraction that is supposed to
strip them, and both rows are written anyway.** m1625a1's mechanics are
sayable without the word, and so are m4323a0's once the leaked name is read
as "whoever summoned this" -- which is a structural fact about that body
rather than anything needing a name. m4323a0 was left out of the first pass
for that reason and added afterwards. Neither word appears here. See #379.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.minions_sa import _kin_within
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_04.minions_sa import _extra_with_advantage
from combat_engine.content.monsters.level_08.brutes import _aura
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
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
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Position,
    Ranged,
    Target,
    Trigger,
    TurnStart,
    When,
    about_me,
    both,
    by_melee,
    leaves_me_out,
    power,
    targets_me,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import has_combat_advantage

_REDUCED_TO_0 = "it is reduced to 0 hit points"


def _nonelemental(c: Cast, who: int | None) -> bool:
    """"Each non-elemental creature in the burst", asked of one creature."""
    return who is not None and not c.is_kind("elemental", on=who)


# ==========================================================================
# m1404
# ==========================================================================


@power(
    "m1404a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m1404a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1569
# ==========================================================================


@power(
    "m1569a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=4, dtype=DamageType.POISON, kind=MINION),
)
def m1569a0(c: Cast) -> None:
    """The second number is the difference, dealt as poison like the first --
    the shared helper deals it untyped, which a poison line cannot use."""
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(1, dtype=DamageType.POISON)


# ==========================================================================
# m1625
# ==========================================================================


@power(
    "m1625a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=6, kind=MINION),
)
def m1625a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1625a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1625a1(c: Cast) -> None:
    """Untyped, and two gates rather than a bonus with a second on top: the
    +1 and the +3 replace each other, where two untyped bonuses would add.
    Asked at the swing, so the company it is keeping is the company it has
    when the blow is rolled. "Another of its own kind" is `Ident.ref`, which
    is the only thing an author is handed to ask it with. Stacking with
    combat advantage needs nothing: that is computed separately.
    """
    mine = _ref_of(c, c.me)

    def helpers(ctx: dict[str, Any]) -> int:
        victim = ctx.get("target")
        if victim is None or ctx.get("ranged"):
            return 0
        beside = c.within(1, of=victim, side="ally")
        if any(_ref_of(c, a) == mine for a in beside):
            return 3
        return 1 if beside else 0

    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: helpers(ctx) == 1,
    )
    c.bonus(
        "attack", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: helpers(ctx) == 3,
    )


# ==========================================================================
# m1881
# ==========================================================================


@power(
    "m1881a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=7, kind=MINION),
)
def m1881a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        for defended in EVERY_DEFENCE:
            c.penalty(defended, 2, until=When.EOTNT)


@power(
    "m1881a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage(bonus=7, dtype=DamageType.NECROTIC, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
)
def m1881a1(c: Cast) -> None:
    """A close burst with no target line is every creature in it."""
    if c.target is not None and c.strike():
        c.hit()


# ==========================================================================
# m1940
# ==========================================================================


@power(
    "m1940a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage(bonus=7, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1940a0(c: Cast) -> None:
    """"If the target is granting combat advantage" is read off the result of
    the blow that was just rolled: asking the board again is too late,
    because a one-shot grant has already been spent by then."""
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(2, dtype=DamageType.NECROTIC)


# ==========================================================================
# m1997
# ==========================================================================


@power(
    "m1997a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=7, kind=MINION),
)
def m1997a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2006
# ==========================================================================


@power(
    "m2006a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 3, kind=MINION),
)
def m2006a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2006a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="granting it combat advantage"),
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 5, kind=MINION),
    requires_text="requires combat advantage against the target",
    dropped=("Target.kind", "c.contract(ref)"),
)
def m2006a1(c: Cast) -> None:
    """The Requirement is about a *pair* and `requires=` is handed a creature
    and no target, so the row picks a victim it does have combat advantage
    against instead of being thrown away when the chooser aims it elsewhere.
    The disease (`x5_17`) has no contraction mechanism to call; the blow and
    the burn both play."""
    victim = _restricted_to(c, 1, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.NECROTIC, on=victim)


# ==========================================================================
# m2082
# ==========================================================================


@power(
    "m2082a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=7, kind=MINION),
)
def m2082a0(c: Cast) -> None:
    """"Only one target at a time" lets the older hold go before the new one
    lands, which is the shape m1157a1 settled on for the same sentence.

    "It can maintain the grab as long as it remains within 2 squares" asks
    for nothing: `Relation.GRABBED_BY` is cleared by an escape and by nothing
    else, so no distance would have broken this grab at one square either --
    the printed clause is a loosening of a rule the engine does not have.
    """
    if not c.strike():
        return
    c.hit()
    label = f"{c.ref} grab"
    for eff in list(c.world.effects.live.values()):
        if eff.label != label or eff.source != c.me or eff.ended:
            continue
        if eff.owner != c.target:
            c.world.effects.end(eff, "it grabs only one target at a time")
    c.grab()


@power(
    "m2082a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target("enemy", 1, label="grabbed by it"),
    keywords=[Keyword.NECROTIC],
    damage=Damage(bonus=10, dtype=DamageType.NECROTIC, kind=MINION),
    dropped=("Target.kind",),
)
def m2082a1(c: Cast) -> None:
    """No attack roll is printed -- the damage simply lands on whoever it is
    holding. The chooser filters on side and count and not on a grab, so the
    row is aimed at its victim rather than returning."""
    held = c.grabbing()
    victim = c.target if c.target in held else next(iter(held), None)
    if victim is not None:
        c.hit(on=victim)


@power(
    "m2082a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2082a2(c: Cast) -> None:
    """Lying still to look like a corpse, seen through by an Insight check
    against a printed DC. Nothing on a board rolls that check and the ruse
    has no consequence either way, so the whole row is inert rather than one
    clause of it."""


# ==========================================================================
# m2503
# ==========================================================================


_M2503_MISSED = "a melee attack misses it"


@power(
    "m2503a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=4, kind=MINION),
)
def m2503a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2503a1",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2503_MISSED,
    on=Trigger(Miss, both(targets_me, by_melee), _M2503_MISSED),
)
def m2503a1(c: Cast) -> None:
    """The card says it makes a melee basic attack, so its own at-will is run
    rather than a second attack line being written here. The +11 and the
    2d6+5 the brief prints against this ref are on no line of the block --
    see the report."""
    who = getattr(c.trigger, "attacker", None)
    if who is not None:
        c.use_power("m2503a0", on=who)


# ==========================================================================
# m2544
# ==========================================================================


@power(
    "m2544a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=8, dtype=DamageType.FIRE, kind=MINION),
)
def m2544a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2544a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_hazards()",),
)
def m2544a1(c: Cast) -> None:
    """The trait m2543a3 already carries, and the same half of it is missing:
    crossing the stuff it lives in for nothing is a label the squares carry,
    but nothing exempts one creature from a hazard's damage."""
    c.ignores_difficult("blood", until=When.ENCOUNTER)


# ==========================================================================
# m2604
# ==========================================================================


@power(
    "m2604a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m2604a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m2604a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d8", 5, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
)
def m2604a1(c: Cast) -> None:
    """The zone goes down on the last target, so it lands once however many
    the burst caught -- and `dsl.use` calls the body once with no target at
    all when the burst is empty, so an explosion with nobody beside it still
    leaves its slime behind.

    "Ends its movement within the zone" is `MoveEnd` and not `MoveStart`:
    where the creature finishes is the whole of the question, and at
    `MoveStart` it has not gone anywhere yet.
    """
    if c.target is not None and c.strike():
        c.hit()
    if not c.last:
        return
    area = frozenset(c.area())
    c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def settled(ev: MoveEnd) -> None:
        who = getattr(ev, "actor", None)
        if who is None:
            return
        pos = c.world.get(who, Position)
        if pos is not None and pos.square in area:
            c.slowed(on=who, until=When.EOTNT)

    c.watch(MoveEnd, settled, until=When.ENCOUNTER, on=c.me, label=c.ref)


# ==========================================================================
# m2605
# ==========================================================================


_M2605_AIMED_AT = "it is the target of a melee or close attack"


@power(
    "m2605a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=5, kind=MINION),
)
def m2605a0(c: Cast) -> None:
    """The card types the power and not the damage, so the blow is untyped
    and the shared helper deals the difference the same way."""
    if c.strike():
        c.hit()
        _extra_with_advantage(c, 2)


@power(
    "m2605a1",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2605_AIMED_AT,
    on=Trigger(AttackDeclared, both(targets_me, by_melee), _M2605_AIMED_AT),
)
def m2605a1(c: Cast) -> None:
    """`by_melee` already answers "melee **or** close": it reads the power's
    own reach and takes melee, close burst and close blast."""
    c.shift(4)


# ==========================================================================
# m2612
# ==========================================================================


@power(
    "m2612a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=9, kind=MINION),
)
def m2612a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2716
# ==========================================================================


@power(
    "m2716a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, kind=MINION),
)
def m2716a0(c: Cast) -> None:
    """The printed parentheticals against a bloodied target are m2716a2
    showing through, and are laid there rather than twice."""
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m2716a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, kind=MINION),
)
def m2716a1(c: Cast) -> None:
    """A printed "10/20" is a normal range and a long one; `Range` holds the
    normal one."""
    if c.strike():
        c.hit()


@power(
    "m2716a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2716a2(c: Cast) -> None:
    """Untyped both times -- the card prints no word in front of either
    "bonus". Both are gated on the victim rather than snapshotting who is
    bloodied now, because a creature crosses that line mid-fight."""

    def against_bloodied(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.bloodied(on=victim)

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=against_bloodied)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=against_bloodied)


# ==========================================================================
# m3803
# ==========================================================================


@power(
    "m3803a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m3803a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3803a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage(bonus=6, dtype=DamageType.PSYCHIC, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
)
def m3803a1(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.hit()


# ==========================================================================
# m3938
# ==========================================================================


@power(
    "m3938a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=9, kind=MINION),
)
def m3938a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3938a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage(bonus=9, kind=MINION),
)
def m3938a1(c: Cast) -> None:
    """The flight comes first and the blow second. "It attacks once at any
    time during its movement" is a choice nothing on the board makes, and
    arriving beside the victim is the use the line is for."""
    c.no_provoke(until=When.EOT)
    c.move(8, at="fly")
    if c.strike():
        c.hit()


@power(
    "m3938a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=14),
    damage=Damage(bonus=9, kind=MINION),
    dropped=("c.kill()",),
)
def m3938a2(c: Cast) -> None:
    """The pull is what the attack roll buys; the 9 is not an attack at all
    and lands on whoever the pull left adjacent, which is why it waits for
    the last target. The damage sits in the header anyway so a rescale can
    find it.

    "This destroys the m3938" is the named gap -- nothing takes a creature
    off the board outright.
    """
    if c.target is not None and c.strike():
        c.pull(2)
    if not c.last:
        return
    for foe in c.within(1, side="enemy"):
        c.hit(on=foe)


# ==========================================================================
# m4030
# ==========================================================================


@power(
    "m4030a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=7, kind=MINION),
)
def m4030a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4030a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=8, kind=MINION),
)
def m4030a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4030a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4030a2(c: Cast) -> None:
    """Asked at the window rather than latched when the trait arms: whether
    it is mounted changes during a fight. `ctx["why"]` is the window's own
    reason, and "moved away" is the one movement opens -- the printed line is
    about moving and not about every opening it might ever get."""
    c.no_provoke(
        until=When.ENCOUNTER,
        when=lambda ctx: c.mount() is not None and ctx.get("why") == "moved away",
    )


# ==========================================================================
# m4037
# ==========================================================================


@power(
    "m4037a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, dtype=DamageType.LIGHTNING, kind=MINION),
)
def m4037a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4037a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=Target("any", 99, everyone=True, label="not elemental"),
    keywords=[Keyword.LIGHTNING],
    damage=Damage(bonus=8, dtype=DamageType.LIGHTNING, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
    dropped=("Target.kind",),
)
def m4037a1(c: Cast) -> None:
    """No attack roll: the burst simply takes whoever is standing in it. The
    origin word is a type and `Target` filters on side and count, so the
    narrowing is gated here and recorded in `label=`."""
    if _nonelemental(c, c.target):
        c.hit()


# ==========================================================================
# m4039
# ==========================================================================


@power(
    "m4039a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=3, dtype=DamageType.FIRE, kind=MINION),
)
def m4039a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m4039a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=Target("any", 99, everyone=True, label="not elemental"),
    keywords=[Keyword.FIRE],
    damage=Damage(bonus=8, dtype=DamageType.FIRE, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
    dropped=("Target.kind",),
)
def m4039a1(c: Cast) -> None:
    if _nonelemental(c, c.target):
        c.hit()


# ==========================================================================
# m4040
# ==========================================================================


@power(
    "m4040a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=7, dtype=DamageType.COLD, kind=MINION),
)
def m4040a0(c: Cast) -> None:
    """"It can shift its speed before making this attack" -- its speed is a
    column, so the number is read rather than written."""
    c.shift(c.speed_of())
    if c.strike():
        c.hit()


@power(
    "m4040a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=Target("any", 99, everyone=True, label="not elemental"),
    keywords=[Keyword.COLD],
    damage=Damage(bonus=8, dtype=DamageType.COLD, kind=MINION),
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
    dropped=("Target.kind",),
)
def m4040a1(c: Cast) -> None:
    if _nonelemental(c, c.target):
        c.hit()


# ==========================================================================
# m4323
# ==========================================================================


@power(
    "m4323a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.spend_action(who, cost)",),
)
def m4323a0(c: Cast) -> None:
    """A body that acts only when its summoner pays for it.

    Written here rather than left out. The brief leaks a printed name
    (#379) and the wave that met it declined the row for that reason,
    which was the right call from where it sat -- but the mechanics do
    not need the word. The sentence is about *whoever summoned this*,
    and that is a structural fact: this body arrives through `m4322a3`
    and the payer is its summoner, not a creature anybody has to name.

    "It cannot attack" is the half with teeth and is laid for the fight.
    The action economy is the gap: nothing charges one creature for
    another's action, which is `c.spend_action(who, cost)` -- the symbol
    `m1438a3` already waits on, where an ally's minor action cannot be
    billed either.

    The third clause, "it uses its summoner's modifiers when relevant",
    is deliberately unmarked. A creature that cannot attack has almost
    no occasion to borrow an attack or damage modifier, so there is no
    second gap to name here -- and one marker names one gap.
    """
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m4461
# ==========================================================================


@power(
    "m4461a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=8, kind=MINION),
)
def m4461a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()
        c.weakened()


# ==========================================================================
# m5642
# ==========================================================================


@power(
    "m5642a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5642a0(c: Cast) -> None:
    """Untyped: the card prints no word before "bonus". `_kin_within` counts
    the caster itself, so "another of its kind adjacent" is two."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER,
        when=lambda _ctx: len(_kin_within(c, 1, c.me)) >= 2,
    )


@power(
    "m5642a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=9, kind=MINION),
)
def m5642a1(c: Cast) -> None:
    """"An attack that does not include it" is `leaves_me_out`, which reads
    the whole target list of the one use -- `ev.target` alone is true of
    every other announcement of a burst that did catch it."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me

    def looked_away(ev: AttackDeclared) -> None:
        if leaves_me_out(c.world, me, ev):
            c.flat(3, on=victim)
            c.shift(1)

    c.on_attack(looked_away, by=victim, until=When.EOTNT, once=True)


@power(
    "m5642a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m5642a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5860
# ==========================================================================


@power(
    "m5860a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m5860a0(c: Cast) -> None:
    """Who is immobilized inside the ring is asked at the moment the turn
    starts: a membership list is stale the moment anybody moves or saves."""
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def starts_inside(ev: TurnStart) -> None:
        who = getattr(ev, "actor", None)
        if who is None or who == c.me or getattr(ev, "ghost", False):
            return
        if who not in c.enemies() or not c.is_(Condition.IMMOBILIZED, on=who):
            return
        if who in c.world.zones.occupants(ring):
            c.flat(3, dtype=DamageType.COLD, on=who)

    c.watch(TurnStart, starts_inside, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m5860a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=8, kind=MINION),
)
def m5860a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOTNT)


# ==========================================================================
# m5999
# ==========================================================================


@power(
    "m5999a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5999a0(c: Cast) -> None:
    """`to="team"` is the widest the relation goes, and the card names nobody
    -- which means whoever is attacking them. `_aura` diffs membership off
    `ZoneEntered`/`ZoneExited`, so the hold comes off at the ring's edge."""
    _aura(
        c,
        1,
        lambda who: who in c.enemies(),
        lambda who: c.grants_advantage(on=who, to="team", until=When.ENCOUNTER),
    )


@power(
    "m5999a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=9, kind=MINION),
)
def m5999a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5999a2",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    trigger=_REDUCED_TO_0,
    on=Trigger(Dropped, about_me, _REDUCED_TO_0),
)
def m5999a2(c: Cast) -> None:
    """One burn of two types, which is `dtypes`: two holds would be two
    saving throws against one printed sentence."""
    if c.target is not None:
        c.ongoing(10, dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC))


# ==========================================================================
# m6138
# ==========================================================================


@power(
    "m6138a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6138a0(c: Cast) -> None:
    c.threatens(2, until=When.ENCOUNTER)


@power(
    "m6138a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=9, kind=MINION),
)
def m6138a1(c: Cast) -> None:
    if c.strike():
        c.hit()
