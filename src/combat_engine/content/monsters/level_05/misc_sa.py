"""Monster abilities, level 5: the blocks that print no role.

Seven stat blocks, twenty-nine rows. A role-less block is usually not an
encounter monster: these are the figures a named character fights *alongside*
-- full defences, a basic attack and one or two tricks, and attack bonuses well
above their level, which is what a companion's card prints and not an error to
correct.

Conventions inherited from the role sweeps at this level and below:

* numbers load from `game.db`; `Attack(vs=AC, printed=11)` is the finished total
  and the engine takes the level back out;
* a **trait** costs no action, has no target, and arms what holds it;
* a printed band of "15/30" takes the short number; no range at all is melee 1;
* an aura that modifies whoever stands in it lays its modifier on the creatures
  and gates on the distance, rather than keeping a membership list that is stale
  the moment either of them moves;
* **`half_on_miss=True` is card data and nothing in the engine reads it**, so a
  Miss line is also written as `else: c.hit(half=True)`. None of these cards
  prints one.

Ten helpers are imported rather than written again; the six written here are the
three aura questions one marking block needs and the two "an ally near me was
caught" predicates two leaders need.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.controllers_sa import _recharge_on_miss
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _edge_damage,
    _triggering_enemy,
)
from combat_engine.content.monsters.level_03.brutes_sa import _press
from combat_engine.content.monsters.level_04.artillery_sa import _shoot_on_the_move
from combat_engine.content.monsters.level_04.misc_sa import (
    _bigger_against_an_opening,
)
from combat_engine.content.monsters.level_04.skirmishers_sa import (
    _against_opportunity,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Size,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    DamageRolled,
    Miss,
    MoveStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, is_, team
from combat_engine.engine.triggers import Trigger, would_hit_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _ally_missed_within(radius: int) -> Any:
    """"An ally within N squares of it misses with an attack."

    `ally_within` reads the *attacker* of the event, which is what this
    sentence is about -- but it says nothing about the distance, so both halves
    are asked here. The caster's own miss is left out: the card says an ally.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


def _ally_beside_hurt(world: World, me: int, ev: Any) -> bool:
    """"An ally adjacent to it is hit by an attack."

    Declared on `DamageRolled` rather than `Hit`, because the row splits the
    blow in two and `Hit` carries no number to split. Its subject is named
    `target`, so `about_me` -- which reads `actor` and only `actor` -- would be
    false here forever.
    """
    victim = getattr(ev, "target", None)
    if victim is None or victim == me:
        return False
    if team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, victim) <= 1


def _warders(c: Cast, ref: str) -> set[int]:
    """This creature and whoever else on its side carries the same aura.

    "...that does not include the m6696 **or another creature that has an
    active m6696a0**" is a set of creatures, and the only thing an author is
    given to compare is the stat block's ref.
    """
    return {c.me, *(a for a in c.allies() if _ref_of(c, a) == ref)}


def _looking_away(c: Cast, ref: str) -> Any:
    """The punished attack: made by an unmarked enemy standing in the aura, at
    nobody who carries the aura.

    `ctx["target"]` is one creature and the printed line says "does not
    *include*", which is the same question asked once per roll -- a 4e attack
    rolls separately against each target, so the per-target reading is the
    printed one rather than an approximation of it.
    """
    me = c.me

    def gate(ctx: dict[str, Any], who: int) -> bool:
        if distance_between(c.world, me, who) > 1:
            return False
        if is_(c.world, who, Condition.MARKED):
            return False
        aimed = ctx.get("target")
        return aimed is not None and aimed not in _warders(c, ref)

    return gate


def _unmarked_shifts_in_aura(world: World, me: int, ev: Any) -> bool:
    """"An unmarked enemy in its aura shifts."

    `MoveStart`, because the enemy has to still be in the aura for the row to be
    true: by `MoveEnd` it has gone and the distance test is false precisely when
    the row should fire. `MoveStart` carries `kind_`, so "shifts" and not "moves"
    is askable, and it is the window an opportunity action belongs in.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "kind_", "") != "shift":
        return False
    if team(world, who) is team(world, me):
        return False
    if is_(world, who, Condition.MARKED):
        return False
    return distance_between(world, me, who) <= 1


def _unmarked_looks_away(world: World, me: int, ev: Any) -> bool:
    """"...or makes an attack that does not include the m6696 or another
    creature that has an active m6696a0 as a target."

    `ev.targets` is the whole list here, so this half really can ask "does not
    include" rather than the per-target question the standing penalty has to
    settle for. **Unmarked means marked by nobody**, which is
    `Condition.MARKED` -- `relations.holds(MARKED_BY, me, who)` is the narrower
    "marked by me" and is the wrong sentence.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if is_(world, who, Condition.MARKED):
        return False
    if distance_between(world, me, who) > 1:
        return False
    from combat_engine.engine.components import Ident
    from combat_engine.engine.query import allies as _allies

    warders = {me}
    for mate in _allies(world, me):
        ident = world.get(mate, Ident)
        if ident is not None and ident.ref == "m6696":
            warders.add(mate)
    return not (set(getattr(ev, "targets", ())) & warders)


# ==========================================================================
# m5090
# ==========================================================================


@power(
    "m5090a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5090a0(c: Cast) -> None:
    """One card printing both halves of what two other blocks at this level
    print as two separate traits."""
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


@power(
    "m5090a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 10),
)
def m5090a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5090a2",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="an ally within 10 squares of it misses with an attack",
    on=Trigger(Miss, _ally_missed_within(10), "an ally nearby misses"),
)
def m5090a2(c: Cast) -> None:
    """The reroll and its bonus are one printed clause, so they go through one
    call: a `c.bonus` laid afterwards is read by the *next* attack and not by
    the one being rerolled. The surge is a second sentence and goes to whoever
    is nearest -- the card says "an ally within 10 squares" and not the one that
    missed."""
    c.reroll_attack(bonus=2)
    mate = next(
        (a for a in c.allies() if distance_between(c.world, c.me, a) <= 10), None
    )
    if mate is not None:
        c.surge(on=mate)


# ==========================================================================
# m6064
# ==========================================================================


@power(
    "m6064a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m6064a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6064a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 7, dtype=DamageType.RADIANT),
)
def m6064a1(c: Cast) -> None:
    """"One ally it can see **chooses**", so the choice is offered rather than
    decided -- `World.decide` takes the head of the list when nobody is
    playing, and the cushion is the safer default of the two."""
    if not c.strike():
        return
    c.hit()
    mate = next((a for a in c.allies() if c.can_see(a)), None)
    if mate is None:
        return
    if (c.choose(["temporary hit points", "a saving throw"]) or
            "temporary hit points") == "temporary hit points":
        c.temp_hp(5, on=mate)
    else:
        c.save(on=mate)


@power(
    "m6064a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 7, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m6064a2(c: Cast) -> None:
    """The Effect line is about allies in the same burst, who are not targets of
    it, so they are read out of the area and the grant is paid once for the whole
    use. `kind="power"` because that is the word the card prints in front of
    "bonus", and two power bonuses do not add."""
    if c.strike():
        c.hit()
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.bonus(AC, 2, on=mate, kind="power", until=When.EONT)


@power(
    "m6064a3",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6064a3(c: Cast) -> None:
    """"The m6064 **or** one ally in the burst" is exactly `ONE_ALLY`, whose
    pool includes the caster. `c.surge` spends the target's own surge and heals
    it, and the extra die is paid on top with `bonus=`."""
    c.surge(bonus=c.roll("1d6"))


# ==========================================================================
# m6472
# ==========================================================================


@power(
    "m6472a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6472a0(c: Cast) -> None:
    _edge_damage(c)


@power(
    "m6472a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6472a1(c: Cast) -> None:
    """Untyped: the card prints a bare "+2 bonus" with no type word, and a
    guessed `kind=` is a number that is quietly too small in every fight."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=_against_opportunity)


@power(
    "m6472a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 5),
)
def m6472a2(c: Cast) -> None:
    """The step is an Effect line, so it is taken whether the blow landed or
    not."""
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m6472a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 5),
)
def m6472a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6472a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6472a4(c: Cast) -> None:
    """The distance is spent in two halves rather than all at once, because "at
    any point during the move" is what brings a creature into reach that one
    step to one destination would not. The printed exemption is from the
    *target's* opportunity attack alone, so it is laid against that creature and
    not against the board."""
    _shoot_on_the_move(c, "m6472a2", 4)


@power(
    "m6472a5",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it is hit by an attack",
    on=Trigger(AttackDeclared, would_hit_me, "an attack would hit it"),
)
def m6472a5(c: Cast) -> None:
    """Declared on `AttackDeclared` rather than on `Hit`: an interrupt resolves
    before the blow, and a reroll announced after the hit has been declared
    changes a number nothing reads again. `keep="new"` is the printed "use the
    second roll, even if it is lower"."""
    c.reroll_attack(keep="new")


# ==========================================================================
# m6479
# ==========================================================================


@power(
    "m6479a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m6479a0(c: Cast) -> None:
    """"Or 1d8 + 11 on a critical hit" **replaces** the damage rather than
    adding to it, and it is a roll -- so it is paid flat, past the engine's own
    rule that a critical maxes the declared dice."""
    if c.strike():
        _crit_line(c, "1d8", 11)


@power(
    "m6479a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m6479a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6479a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3, kind=LIMITED),
    dropped=("c.cannot_attack(opportunity=)",),
)
def m6479a2(c: Cast) -> None:
    """`c.cannot_attack` takes a whole creature or one named victim away and has
    no way to say "opportunity attacks only", so that clause is named rather
    than widened -- forbidding every attack for a round is a far bigger thing
    than the card prints."""
    if c.strike():
        _crit_line(c, "1d8", 19)


@power(
    "m6479a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:nature",),
)
def m6479a3(c: Cast) -> None:
    """Talking to crows and ravens is the narrative clause: no board rolls
    Nature, and the circumstance -- being understood by birds -- never comes up
    in a fight, so a verb to hold it would be a mechanism nobody could ever
    pass a purpose to. Merging equipment is the same sentence from the other
    end and is already what a form does here.

    Everything with combat meaning plays: the size, the flight and the muteness.
    All three hang off the form, so stepping out of it -- a minor action, which
    is `revert=` -- puts them all back at once rather than leaving a Tiny mute
    creature standing there."""
    shape = c.form(modes={"fly": 8}, revert=MINOR, label=c.ref)
    for held in (
        c.resize(Size.TINY, on=c.me, until=When.ENCOUNTER),
        c.cannot_attack(on=c.me, until=When.ENCOUNTER),
    ):
        if held is not None:
            shape.on_end.append(
                lambda h=held: c.world.effects.end(h, "it changed back")
            )


@power(
    "m6479a4",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6479a4(c: Cast) -> None:
    c.surge()


# ==========================================================================
# m6492
# ==========================================================================


@power(
    "m6492a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 7),
)
def m6492a0(c: Cast) -> None:
    """The bigger die is read off the result of the swing that has just been
    rolled. Asking the board again is too late: a one-shot grant has already
    been spent by then, and the bigger die would be paid on half the attacks
    that earned it."""
    if c.strike():
        _bigger_against_an_opening(c, "1d4", "3d4", 7)


# ==========================================================================
# m6545
# ==========================================================================


@power(
    "m6545a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m6545a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether the blow did or not."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6545a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m6545a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6545a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m6545a2(c: Cast) -> None:
    """The die stays in the header because that is what `actions.recharge` rolls
    and what the card shows; "Recharge if the attack misses" is the printed
    sentence on top of it, and the two only ever agree to make the row available
    sooner. Slowed and unable to shift are one effect, because that is what makes
    one saving throw end both."""
    _recharge_on_miss(c)
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, Condition.CANNOT_SHIFT, until=When.SAVE_ENDS
        )


@power(
    "m6545a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
)
def m6545a3(c: Cast) -> None:
    """The penalty is the price of the guard and is paid on itself, so both go
    on `c.me` -- `c.penalty` follows the target, which for a `SELF` row is this
    creature anyway, and naming it is what keeps that readable. `c.resist` with
    no type at all is "resist 5 to all damage"."""
    c.penalty("attack", 2, on=c.me, until=When.EONT)
    c.resist(5, on=c.me, until=When.EONT)


@power(
    "m6545a4",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an ally adjacent to it is hit by an attack",
    on=Trigger(DamageRolled, _ally_beside_hurt, "an ally beside it is hurt"),
)
def m6545a4(c: Cast) -> None:
    """`c.halve` reports how much it took off, which is exactly the share this
    creature shoulders -- "the other half" is the part that was spared and not
    half of what is left."""
    spared = c.halve()
    if spared > 0:
        c.flat(spared, on=c.me)


# ==========================================================================
# m6696
# ==========================================================================


@power(
    "m6696a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6696a0(c: Cast) -> None:
    """The aura is drawn for the board and the penalty is laid on the enemies,
    gated on all three printed narrowings: standing in it, unmarked, and
    swinging at nobody who carries it. A stored membership list would be stale
    the moment either creature moved, and a mark arrives as a relation rather
    than as a condition, so it has to be asked and not watched for."""
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    gate = _looking_away(c, "m6696")
    for foe in c.enemies():
        c.penalty(
            "attack",
            2,
            on=foe,
            until=When.ENCOUNTER,
            when=lambda ctx, f=foe: gate(ctx, f),
        )


@power(
    "m6696a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 7),
)
def m6696a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6696a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m6696a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m6696a3",
    level=5,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1),
    keywords=[Keyword.HEALING],
)
def m6696a3(c: Cast) -> None:
    """"It loses a healing surge, and **if it does**" -- so the heal is paid out
    of `c.spend_surge`'s answer and nothing happens when there is none left. A
    monster carries one surge per tier for exactly this kind of line.
    `c.spend_surge` is the caster's and `c.save` is the target's, which is the
    split on both sides of this sentence."""
    if c.spend_surge(on=c.me):
        c.heal(20)
        c.save()


@power(
    "m6696a4",
    level=5,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    trigger="an unmarked enemy in its aura shifts, or attacks nobody who carries the aura",
    on=(
        Trigger(MoveStart, _unmarked_shifts_in_aura, "an enemy shifts out of its aura"),
        Trigger(AttackDeclared, _unmarked_looks_away, "an enemy in its aura looks away"),
    ),
)
def m6696a4(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- declaring half of this
    looks finished and fires on one of the two moments the card names.

    **`MoveStart` and not `MoveEnd`.** The enemy has to still be *in the aura*
    for the row to be true, and by `MoveEnd` it has left: the adjacency test is
    false precisely when the row should fire. `MoveStart` carries `kind_` and is
    the interrupt window an opportunity action belongs in.

    Nine radiant damage and no attack roll, which is what the card prints."""
    foe = _triggering_enemy(c)
    if foe is not None and foe in _press(c, 1):
        c.flat(9, dtype=DamageType.RADIANT, on=foe)
