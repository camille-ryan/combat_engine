"""Monster abilities, level 2, artillery: the second sweep.

Sixteen stat blocks whose rows were still undeclared. `artillery.py` holds the
first sweep of this level; the split is by *when* the work was done rather
than by what the creatures are, and the conventions are the ones the level-1
sweep settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a printed range of "15/30" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty;
* a blow of two damage types keeps the **first** in the header and carries
  the rest as keywords, which is what one `Damage` can say;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`.

Two helpers come from `level_01/artillery_sa.py` and one from
`level_02/skirmishers.py` rather than being copied: the same printed sentences
turn up again here. Five helpers below are shared the other way, with
`brutes_sa.py`, which imports them -- four printed lines are word for word the
same on blocks of both roles.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
    _uncovered,
)
from combat_engine.content.monsters.level_02.skirmishers import (
    _still_hidden_on_a_miss,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
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
    Defense,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    ConditionApplied,
    Hit,
    Miss,
    RelationSet,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, creatures, distance_between, team
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_me,
    by_melee,
    hits_me,
    targets_me,
)

#: The four defences, for the rows whose bonus is to all of them at once.
ALL_DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)


def _trap_shield(c: Cast) -> None:
    """"+2 bonus to all defences against traps."

    Three blocks across the two roles print this word for word. Asked of the
    attack context rather than armed and disarmed around every trap, because
    `c.is_trap` falls through to `c.target` when handed None -- which inside a
    defender's own modifier is the wrong creature entirely.
    """

    def sprung(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.is_trap(who)

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER, when=sprung)


def _minor_shift(c: Cast) -> None:
    """"The creature shifts 1 square as a minor action."

    A printed power rather than a trait: the action cost is in the header and
    the body is the step. Two blocks here and two in `brutes_sa.py` print it.
    """
    c.shift(1)


def _extra_against_advantage(c: Cast, dice: str) -> None:
    """"An extra 1d6 damage against a target it has combat advantage against."

    A gate on the damage context, which carries `advantage`, rather than a
    hold put on and taken off: a one-shot grant is already spent by the time
    the blow is rolled, so asking the board again comes back false.
    """
    c.bonus(
        "damage",
        0,
        dice=dice,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


def _saves_off_prone(c: Cast) -> None:
    """"A saving throw to avoid falling prone when an attack would knock it".

    Two blocks across the two roles print this. `Effects.apply` installs the
    hold before it announces, which is what makes ending one from inside
    `ConditionApplied` safe, and `Effects.save` rolls, announces and ends --
    so the printed saving throw is a real one and a failure leaves the
    creature prone.
    """
    me = c.me

    def brace(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.PRONE or ev.target != me:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.PRONE in eff.conditions:
                c.world.effects.save(eff)
                return

    c.watch(
        ConditionApplied, brace, until=When.ENCOUNTER, on=me, label=f"{c.ref} footing"
    )


def _ally_target_within(squares: int):  # noqa: ANN202
    """The creature that was *hit* is an ally of mine, within range.

    `ally_within` reads the attacker and `enemy_target_within` wants the other
    side, so "when an ally within 5 squares is hit" could be asked of neither.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def _marked_me(world: World, me: int, ev: Any) -> bool:
    """A mark arrives as a `RelationSet` and is never announced as a condition,
    so a row of this shape declared on `ConditionApplied` never fires."""
    return getattr(ev, "kind_", None) is Relation.MARKED_BY and ev.target == me


def _an_ally_is_down(world: World, eid: int) -> bool:
    """A Requirement that there is a body on the floor to pick up.

    `Target` filters on side and size and says nothing about whether a
    creature is alive, so the restriction is asked here as well as in the
    body: without it the row is offered every turn, aimed at whoever is
    nearest, and comes back having done nothing -- which from the outside is
    indistinguishable from a row written wrong.
    """
    return any(
        not alive(world, other)
        and other != eid
        and team(world, other) is team(world, eid)
        for other in creatures(world)
    )


# --------------------------------------------------------------------------
# m1650
# --------------------------------------------------------------------------


@power(
    "m1650a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
)
def m1650a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1650a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m1650a1(c: Cast) -> None:
    """Printed 10/20; the normal band is the one declared, so the creature
    shoots from where it takes no penalty."""
    if c.strike():
        c.hit()


@power(
    "m1650a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1650a2(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m1650a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1650a3(c: Cast) -> None:
    _extra_against_advantage(c, "1d6")


@power(
    "m1650a4",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m1650a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m1655
# --------------------------------------------------------------------------


@power(
    "m1655a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m1655a0(c: Cast) -> None:
    """The cold half is a second roll of its own type, so it cannot sit in a
    header that holds one `Damage`."""
    if c.strike():
        c.hit()
        c.damage("1d4", dtype=DamageType.COLD)


@power(
    "m1655a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2),
)
def m1655a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)


@power(
    "m1655a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 1, dtype=DamageType.COLD, kind=LIMITED),
)
def m1655a2(c: Cast) -> None:
    """An area attack against AC is unusual and is what the block prints."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3220
# --------------------------------------------------------------------------


@power(
    "m3220a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
)
def m3220a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3220a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 4),
)
def m3220a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3220a2",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is marked",
    on=Trigger(RelationSet, _marked_me, "it is marked"),
)
def m3220a2(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)


# --------------------------------------------------------------------------
# m3545
# --------------------------------------------------------------------------


@power(
    "m3545a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 2),
)
def m3545a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3545a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m3545a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3545a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3545a2(c: Cast) -> None:
    """"Grants combat advantage to it" and "it has combat advantage against"
    are the same question from the two ends, and the damage context answers it
    once."""
    _extra_against_advantage(c, "1d6")


@power(
    "m3545a3",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m3545a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m3545a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3545a4(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


# --------------------------------------------------------------------------
# m3564
# --------------------------------------------------------------------------


@power(
    "m3564a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
)
def m3564a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3564a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m3564a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3564a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.kill()",),
)
def m3564a2(c: Cast) -> None:
    """A critical hit ends the creature outright whatever its hit points.

    Nothing says "reduce to 0 hit points". `c.flat` of a large number is a
    *blow*, which resistance, temporary hit points and immunity all read, and
    this is none of those. The whole trait is the one missing verb, so the row
    is refused in play rather than half written.
    """


# --------------------------------------------------------------------------
# m4113
# --------------------------------------------------------------------------


@power(
    "m4113a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m4113a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4113a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 3),
)
def m4113a1(c: Cast) -> None:
    """"Grants combat advantage to allies" is the whole side, so `to="team"`:
    `"ally"` leaves the creature itself out of its own line."""
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.EONT)


@power(
    "m4113a2",
    level=2,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger="when an ally within 5 squares is hit by a melee attack",
    on=Trigger(
        Hit,
        both(_ally_target_within(5), by_melee),
        "an ally within 5 squares is hit by a melee attack",
    ),
)
def m4113a2(c: Cast) -> None:
    """The burst is centred on the **ally that was hit**, which no `Range` can
    say -- `from_` names a companion and nothing else. So the row declares no
    target and takes the centre off its own trigger, which is the only place
    that creature is written down.
    """
    hurt = getattr(c.trigger, "target", None)
    if hurt is None:
        return
    bonus = c.world.scaling.trim(5, c.level)
    for victim in c.within(2, of=hurt, side="enemy"):
        if c.attack(bonus, REF, on=victim):
            c.damage("1d10", 3, dtype=DamageType.POISON, on=victim)
            c.ongoing(5, DamageType.POISON, on=victim)


@power(
    "m4113a3",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m4113a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4178
# --------------------------------------------------------------------------


@power(
    "m4178a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
)
def m4178a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m4178a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2),
)
def m4178a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4178a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4178a2(c: Cast) -> None:
    """Two swings and a step. `c.use_power` runs the other row at this row's
    action cost, so the printed pair are the *same* attacks the creature makes
    on its own and every rider that reads one still does."""
    c.use_power("m4178a1", on=c.target)
    if c.last:
        c.shift(1)


@power(
    "m4178a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("3d6", 2, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m4178a3(c: Cast) -> None:
    """"Recharges when first bloodied" on top of the die the database files:
    the two only ever agree to put the row back sooner."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(1)
    else:
        c.hit(half=True)


@power(
    "m4178a4",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE),
)
def m4178a4(c: Cast) -> None:
    """The splash is "any creature adjacent to the target", which takes in the
    creature's own allies and leaves the target itself out."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    for near in c.within(1, of=victim, side="any"):
        if near not in (c.me, victim):
            c.damage("1d6", dtype=DamageType.FIRE, on=near)


# --------------------------------------------------------------------------
# m4502
# --------------------------------------------------------------------------


@power(
    "m4502a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 1),
)
def m4502a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4502a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m4502a1(c: Cast) -> None:
    """"If it ends its next turn closer than where it began" is measured, not
    guessed: the distance is taken at the start of the target's next turn and
    compared at the end of it. `MoveEnd` cannot answer this -- the creature may
    step away and back, and the printed line is about where it finishes.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    me = c.me
    opened: dict[int, int] = {}

    def began(ev: TurnStart) -> None:
        if ev.actor == victim:
            opened[victim] = distance_between(c.world, me, victim)

    def ended(ev: TurnEnd) -> None:
        if ev.actor != victim or victim not in opened:
            return
        if distance_between(c.world, me, victim) < opened.pop(victim):
            c.flat(3, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(TurnStart, began, until=When.EOTNT, on=victim, label=f"{c.ref} closing")
    c.watch(TurnEnd, ended, until=When.EOTNT, on=victim, label=f"{c.ref} closed")


@power(
    "m4502a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def m4502a2(c: Cast) -> None:
    """The ally runs in and swings. The extra damage is laid on the ally for
    the length of this turn so that it rides the charge rather than whatever
    the ally does next on its own account."""
    friend = c.target
    if friend is None:
        return
    victim = min(
        (foe for foe in c.enemies() if alive(c.world, foe)),
        key=lambda foe: distance_between(c.world, friend, foe),
        default=None,
    )
    if victim is None:
        return
    c.bonus("damage", 3, on=friend, until=When.EOT)
    c.charge_at(victim, who=friend)


@power(
    "m4502a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m4502a3(c: Cast) -> None:
    """Six against a prone target rather than three plus three: two bonuses of
    one kind do not add, so the gated pair has to be 3 and 6. Written as 3 plus
    a second 3 it would come to 3 forever and look like a working line."""
    friend = c.target
    if friend is None:
        return
    victim = min(
        (foe for foe in c.enemies() if distance_between(c.world, friend, foe) <= 1),
        key=lambda foe: distance_between(c.world, friend, foe),
        default=None,
    )
    if victim is None:
        return
    extra = 6 if c.is_(Condition.PRONE, on=victim) else 3
    c.grant_attack(friend, on=victim, damage_bonus=extra)


@power(
    "m4502a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 1, kind=LIMITED),
)
def m4502a4(c: Cast) -> None:
    """"1d4 random creatures in the burst" is a *count* rolled at use time and
    no `Target` holds one -- `UpTo(4)` lets the chooser take four every time.
    So the row declares no target and takes as many as the roll allows out of
    everything standing in the burst, itself excepted.
    """
    _recharge_when_bloodied(c)
    bonus = c.world.scaling.trim(5, c.level)
    crowd = [who for who in c.within(1, side="any") if who != c.me]
    for victim in crowd[: c.roll("1d4")]:
        if c.attack(bonus, AC, on=victim):
            c.damage("1d10", 1, on=victim)
            c.prone(on=victim)


@power(
    "m4502a5",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=Target(side="ally", count=1, label="one dead ally"),
    keywords=[Keyword.HEALING],
    requires=_an_ally_is_down,
    requires_text="an ally must be dead",
    dropped=("Condition.DEAD",),
)
def m4502a5(c: Cast) -> None:
    """"One **dead** ally" is a restriction `Target` cannot carry **yet**.

    Re-aimed from `Target.condition`, which now resolves -- the field landed, so
    this row would otherwise have reported itself finished. Dead is not a
    `Condition` at all today: it is `Health`, and `Condition.DYING` is a
    different state. So `conditions=frozenset({Condition.DEAD})` is the spelling
    this wants and the member does not exist. Camille asked for it on #399,
    which is what the marker now names. Until then the restriction stays in
    `label=`, asked again here, and gated by `requires=`."""
    friend = c.target
    if friend is None or alive(c.world, friend):
        return
    if c.reanimate(on=friend, hp=1):
        c.grant_action("stand", FREE, on=friend)


# --------------------------------------------------------------------------
# m4611
# --------------------------------------------------------------------------


@power(
    "m4611a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING),
)
def m4611a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4611a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.LIGHTNING,
        Keyword.NECROTIC,
        Keyword.THUNDER,
        Keyword.ACID,
        Keyword.FIRE,
    ],
)
def m4611a1(c: Cast) -> None:
    """One roll chooses between three attacks with three defences, three target
    counts and two different shapes -- one more branch than `attack_alt` holds
    and two more `reach`es. So the row declares the range it mostly uses and
    rolls its own targets; the bonus goes through `scaling.trim` exactly as the
    header would have taken it.
    """
    bonus = c.world.scaling.trim(7, c.level)
    roll = c.roll("1d6")
    foes = [foe for foe in c.enemies() if c.distance(foe) <= 10 and c.can_see(foe)]
    if not foes:
        return
    if roll <= 2:
        if c.attack(bonus, REF, on=foes[0]):
            c.damage(
                "1d8",
                3,
                dtypes=(DamageType.LIGHTNING, DamageType.NECROTIC),
                on=foes[0],
            )
            c.dazed(until=When.SAVE_ENDS, on=foes[0])
    elif roll <= 4:
        for victim in foes[:2]:
            if c.attack(bonus, FORT, on=victim):
                c.damage("1d10", 3, dtype=DamageType.THUNDER, on=victim)
                c.push(3, on=victim)
    else:
        centre = next((friend for friend in c.allies() if c.is_minion(friend)), None)
        if centre is None:
            return
        for victim in c.within(1, of=centre, side="any"):
            if victim != c.me and c.attack(bonus, REF, on=victim):
                c.damage(
                    "2d10", 3, dtypes=(DamageType.ACID, DamageType.FIRE), on=victim
                )


@power(
    "m4611a2",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m4611a2(c: Cast) -> None:
    """"No more than three per encounter" is a count that has to survive
    between uses, and a body keeps nothing. Each call leaves a marker effect
    behind, so the tally is the number of markers -- which is the cap as
    printed, and not "three alive at once", which is a weaker thing.
    """
    label = f"{c.ref} summoned"
    spent = sum(1 for eff in c.world.effects.of(c.me) if eff.label == label)
    if spent >= 3:
        return
    if c.summon("m3054") > 0:
        c.effect(label, until=When.ENCOUNTER, on=c.me)


@power(
    "m4611a3",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is missed by an attack",
    on=Trigger(Miss, targets_me, "it is missed by an attack"),
)
def m4611a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5428
# --------------------------------------------------------------------------


@power(
    "m5428a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 1),
)
def m5428a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.ACID)


@power(
    "m5428a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d4", 1),
)
def m5428a1(c: Cast) -> None:
    """Asked *before* the row's own slow lands: afterwards every target is
    "already slowed" and the line escalates every single time."""
    stuck = c.is_(Condition.SLOWED)
    if not c.strike():
        return
    c.hit()
    if stuck:
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)
    c.ongoing(5, DamageType.ACID)


# --------------------------------------------------------------------------
# m5441
# --------------------------------------------------------------------------


@power(
    "m5441a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5441a0(c: Cast) -> None:
    """The slide is at the end of the enemy's turn and the aura is read then,
    not when the turn began -- a creature that walked out is out."""
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def finished(ev: TurnEnd) -> None:
        if ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor):
            c.slide(2, on=ev.actor)

    c.watch(TurnEnd, finished, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5441a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 2),
)
def m5441a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5441a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE, half_on_miss=True),
)
def m5441a2(c: Cast) -> None:
    """Fire *and* force: the header keeps the first type and the keywords carry
    the pair, which is the convention the level-3 sweep settled."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5441a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d10", 2, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5441a3(c: Cast) -> None:
    """`c.flat` for the extra force and not `c.damage`: a rolled die inside a
    critical branch is maximised, and the printed 5 is a flat 5."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(5, dtype=DamageType.FORCE)
            c.prone()


@power(
    "m5441a4",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage(
        "2d6", 11, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True
    ),
)
def m5441a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.condition(Condition.DEAFENED, until=When.EONT)


@power(
    "m5441a5",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    trigger="when it misses with an attack roll",
    on=Trigger(Miss, by_me, "it misses with an attack roll"),
)
def m5441a5(c: Cast) -> None:
    """"Taking either result" is a choice, so `keep="best"`: the creature is the
    one choosing and it has already paid its allies for the privilege."""
    for friend in c.within(20, side="ally"):
        c.flat(5, dtype=DamageType.NECROTIC, on=friend)
    c.reroll_attack(keep="best")


@power(
    "m5441a6",
    level=2,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it is hit by a close or area attack that also targets an ally",
    on=Trigger(Hit, targets_me, "it is hit by a close or area attack"),
    dropped=("Hit.origin",),
)
def m5441a6(c: Cast) -> None:
    """The ally clause **is** askable; only the escape is not.

    `Hit` carries one `target` as a declared field, but `resolve.attack` also
    stamps `among` on it -- the whole target list of the one use -- and
    `triggers.leaves_me_out` already reads it. So "that also includes one of its
    allies as a target" is a real test, not a gap, and the two markers this row
    carried were both wrong: `Hit.all_targets` named something that exists, and
    `c.area_of(ev)` matched `dsl.area_of`, which exists and is not what is
    wanted -- `todo.py` reported that as an arrival and went red on it.

    What is genuinely absent is the **origin square** the area was aimed at.
    `dsl.area_of` can say which squares an area covers given one; no outcome
    event carries it, so "if it ends this shift outside the area of the
    triggering attack, the attack does not hit it" cannot be measured and the
    `c.cancel()` it licenses is not taken. That is `Hit.origin`.
    """
    hitter = get(getattr(c.trigger, "power", ""))
    if hitter is None or hitter.reach.kind not in (
        "close_burst",
        "close_blast",
        "area_burst",
    ):
        return
    # The printed trigger narrows to an attack that caught an ally too.
    caught = set(getattr(c.trigger, "among", ()) or ())
    if not (caught - {c.me}) & set(c.allies()):
        return
    c.shift(c.speed_of(c.me))


# --------------------------------------------------------------------------
# m5844
# --------------------------------------------------------------------------


@power(
    "m5844a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5844a0(c: Cast) -> None:
    """Asked of the attack context, so the answer is read at the moment of the
    swing and follows everybody around the board on its own."""
    me = c.me

    def flanked(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(
            friend != me and distance_between(c.world, friend, victim) <= 1
            for friend in c.allies()
        )

    c.gains_advantage(flanked, until=When.ENCOUNTER, on=me)


@power(
    "m5844a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5844a1(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m5844a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 2),
)
def m5844a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5844a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 7),
)
def m5844a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5844a4",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=6),
)
def m5844a4(c: Cast) -> None:
    """No damage line at all: the whole hit is the hold and the burn."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
        c.ongoing(5)


@power(
    "m5844a5",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when an enemy hits it",
    on=Trigger(Hit, hits_me, "an enemy hits it"),
)
def m5844a5(c: Cast) -> None:
    """"Use the new result" -- the enemy is the one rerolling and has no say in
    it, so `keep="new"` rather than the creature's own `best`."""
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6507
# --------------------------------------------------------------------------


@power(
    "m6507a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.reload()",),
)
def m6507a0(c: Cast) -> None:
    """The whole trait is a cheaper reload, and loading is not a cost the
    engine charges -- so there is nothing to make cheaper and no way to say the
    sentence. Three class rows wait on the same verb."""


@power(
    "m6507a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 4),
)
def m6507a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6507a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
)
def m6507a2(c: Cast) -> None:
    """The Effect is not conditional on the hit, so the step is handed over
    whether the shot lands or not."""
    if c.strike():
        c.hit()
    friend = next((who for who in c.allies() if c.can_see(who)), None)
    if friend is not None:
        c.grant_action("shift", FREE, on=friend)


@power(
    "m6507a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m6507a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6507a4",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when an arcane attack hits it",
    on=Trigger(Hit, targets_me, "an arcane attack hits it"),
)
def m6507a4(c: Cast) -> None:
    """The keyword is read off the row that swung rather than declared with
    `by_keyword`, which would have to be combined with `targets_me` anyway;
    this way the one refusal is visible in one place."""
    hitter = get(getattr(c.trigger, "power", ""))
    if hitter is not None and Keyword.ARCANE in hitter.keywords:
        c.temp_hp(10, on=c.me)


# --------------------------------------------------------------------------
# m6599
# --------------------------------------------------------------------------


@power(
    "m6599a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 4, kind=MINION),
)
def m6599a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6599a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 4, kind=MINION),
)
def m6599a1(c: Cast) -> None:
    """"Or 6 if the target has no cover" is the greater of two flat numbers,
    which one `Damage` cannot hold. The header keeps the printed 4 so MM3
    rescaling still reads it and the extra 2 is laid on top."""
    uncovered = _uncovered(c, c.target)
    if c.strike():
        c.hit()
        if uncovered:
            c.flat(2)


# --------------------------------------------------------------------------
# m6623
# --------------------------------------------------------------------------


@power(
    "m6623a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6623a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m6623a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6623a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6623a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3),
)
def m6623a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6623a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m6623a3(c: Cast) -> None:
    """Cover is measured before the shot: it is a fact about two positions and
    both of them are where they were when the trigger was pulled."""
    uncovered = _uncovered(c, c.target)
    if c.strike():
        c.hit()
        if uncovered:
            c.damage("1d6", dtype=DamageType.PSYCHIC)


# --------------------------------------------------------------------------
# m856
# --------------------------------------------------------------------------


@power(
    "m856a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d4", 3),
)
def m856a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m856a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3),
)
def m856a1(c: Cast) -> None:
    """The plain shot -- what the creature throws once the loaded rounds are
    gone. The loaded variant is `m856a2`, which is its own row with its own
    three uses, so the printed cross-reference is in the tree rather than
    folded in here twice."""
    if c.strike():
        c.hit()


@power(
    "m856a2",
    level=2,
    usage=AT_WILL,
    uses=3,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3),
)
def m856a2(c: Cast) -> None:
    """Three rounds carried, one effect each. `uses=3` is the ammunition and
    `m856a1` is what the creature falls back to when they are gone.

    The effect is chosen rather than rolled: the block says "chosen from the
    types listed below", so it is the creature's to pick.
    """
    if not c.strike():
        return
    c.hit()
    pick = c.choose(["penalty", "burn", "hold"], "which round")
    if pick == "burn":
        c.ongoing(2, DamageType.FIRE)
    elif pick == "hold":
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m856a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m856a3(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m856a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m856a4(c: Cast) -> None:
    _trap_shield(c)
