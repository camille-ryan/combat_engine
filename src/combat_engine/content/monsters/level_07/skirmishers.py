"""Monster abilities, level 7: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=12)` and `Damage("2d4", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the six levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or triggered actions and are written as such; a printed range
of "10/20" takes the **normal** range; a stat block that prints no range at
all means melee 1; and a row that moves and swings takes the swing first,
because the movement picks its own destination and one taken first can leave
the target out of reach. The three rows here that name their order outright
-- "before the attack, it shifts", "teleports, attacks, and teleports
again", "attacks, shifts, attacks" -- say so, and are written as printed.

Four things this level needed that the levels below did not. **A burst that
is thrown from somewhere else**: two rows shift and then attack from where
they land, and a header's targets are chosen before the body runs, so those
rows declare `NO_TARGET` and pick their own once the step is taken -- the
arrangement m4916a3 already used for a burst that grants rather than
attacks. **Who landed the blow that finished somebody**: `Bloodied` and
`Dropped` name the creature that went down and not the one that put it
there, so "it bloodies an enemy or drops an enemy" is declared on
`DamageApplied`, which carries `source`, the hit points left and the size of
the blow -- everything the printed sentence asks. **A crit range printed on
an attack line rather than as a trait**: `crit_range` is read as a modifier
at the moment of the roll, so it is installed once, gated on the row's own
ref, and guarded against a second install by its label. And **a rider that
swings instead of its mount**: the mount's flying attack and the printed
substitution are two different rows, and `PowerUsed` is announced before the
body runs -- so the trait lays a one-shot hold and the row that would swing
reads it.

The helpers that hide, that charge, that fly, that count a crowd, that fire
a row and report what it hit, and that recharge on a printed sentence rather
than on a die were written for levels 2 to 6 and are imported rather than
copied.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.monsters.level_02.skirmishers import _had_advantage
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _is_bloodied,
    _recharge_on,
)
from combat_engine.content.monsters.level_04.skirmishers import (
    _basic_ref,
    _guarded_move,
    _has_advantage,
    _struck,
    _until_the_grab_ends,
)
from combat_engine.content.monsters.level_05.skirmishers import (
    _MELEE_KINDS,
    _fly_speed,
    _reach_kind,
)
from combat_engine.content.monsters.level_06.brutes import _same_row
from combat_engine.content.monsters.level_06.skirmishers import (
    _after_moving,
    _mobbed,
    _renew,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
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
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    Square,
    Stats,
    Usage,
    When,
    Window,
    World,
    distance,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Hit,
    MoveEnd,
    OpportunityWindow,
    PowerUsed,
    RelationSet,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    enemies,
    has_combat_advantage,
    is_,
    moving_as,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_opportunity,
    targets_me,
)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (AC, FORT, REF, WILL)


def _taking_ongoing(c: Cast, who: int | None) -> bool:
    """Is that creature burning, from anybody and of any kind?

    Asked of the effect table rather than of anything an attack carries: the
    printed clause is about the target's condition and says nothing about
    where the damage came from.
    """
    return who is not None and any(
        eff.ongoing is not None for eff in c.world.effects.of(who)
    )


def _worst_burn(c: Cast, who: int) -> Effect | None:
    """The heaviest ongoing damage that creature is carrying.

    A printed line reading "increases the ongoing damage by 5" names one
    number and a creature can be carrying two, each with its own saving
    throw. Raising both would pay the rider twice for one blow, so the
    largest is the one raised -- the one the printed line is plainly about.
    """
    burning = [e for e in c.world.effects.of(who) if e.ongoing is not None]
    return max(burning, key=lambda e: e.ongoing[0]) if burning else None


def _dodges_openings(c: Cast, amount: int = 2) -> None:
    """Better AC against opportunity attacks, and nothing else.

    A gate on the modifier rather than something put on and taken off,
    because the attack context carries `opportunity`. Racial, so it does not
    displace a power bonus to the same defence. `amount` is the printed
    number: two here, five on one of the level 8 stat blocks.
    """
    c.bonus(
        AC,
        amount,
        until=When.ENCOUNTER,
        on=c.me,
        kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


def _sapping_aura(c: Cast, radius: int, amount: int) -> None:
    """An aura whose occupants are worse at defending themselves.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the penalty should go on
    and come off. The defences ride one effect so they end together.
    Whoever is already standing inside is caught separately at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    me, ref = c.me, c.ref
    held: dict[int, Effect] = {}
    ring = c.aura(radius, until=When.ENCOUNTER, label=ref)

    def sap(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        held[who] = c.world.effects.apply(
            who,
            me,
            When.ENCOUNTER,
            label=ref,
            mods=[
                (who, Mod(what=d.value, value=-amount, kind="untyped", label=ref))
                for d in DEFENCES
            ],
        )

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            sap(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{ref} out")
    for actor in c.world.zones.occupants(ring):
        sap(actor)


def _while_watching(c: Cast, ref: str, run: Callable[[], None]) -> list[int]:
    """Run something and report whom the named row hit while it ran.

    `_struck` fires a row and counts its own hits; this is the other half of
    the same trick, for a row whose Effect line uses a *second* row that
    attacks somewhere inside itself -- the hits are announced under the
    inner ref, which is the one worth watching.
    """
    hits: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.power == ref:
            hits.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        run()
    finally:
        c.world.bus.off(sub)
    return hits


def _hurt_by_an_attack(world: World, me: int, ev: DamageApplied) -> bool:
    """Damage that came off an attack rather than off a burn or a zone.

    The printed trigger is "is hit by an attack", which `Hit` says outright
    -- but `Hit` is announced *before* the damage is applied, and the row
    that needs this has to know whether the blow bloodied it. So the
    damage event is the trigger and the attack half is asked of the row
    behind it.
    """
    from combat_engine.engine.dsl import get

    p = get(getattr(ev, "detail", "") or "")
    return p is not None and p.attack is not None


def _flying(world: World, eid: int) -> bool:
    """Is this creature in the air **right now**?

    `Movement.modes` only ever said what it could do, which makes a printed
    "Requirement: it must be flying" true for anything with a fly speed at
    all. `Movement.using` is what it is doing, and `movement.settle` puts a
    flyer down at the end of its turn, which is where the flag is cleared.
    """
    return moving_as(world, eid, "fly")


def _a_prone_enemy(world: World, eid: int) -> bool:
    return any(is_(world, foe, Condition.PRONE) for foe in enemies(world, eid))


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m2857
# --------------------------------------------------------------------------


@power(
    "m2857a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 5),
)
def m2857a0(c: Cast) -> None:
    """No range is printed, which the levels below settled means melee 1."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2857a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2857a1(c: Cast) -> None:
    """Blink in, swing, and blink out again if it landed.

    The printed order is named outright and the second teleport is
    conditional on the swing, so the usual arrangement -- swing first,
    because movement picks its own destination -- is not the printed one and
    is not taken. The row declares no target for the same reason: the blade
    is used after the jump, so it picks its own from wherever it arrives.

    `_struck` says whom the inner row actually *hit*, where `use` says only
    that it went off -- which is the whole of the printed condition.
    """
    c.teleport(5)
    if _struck(c, "m2857a0", 1):
        c.teleport(5)


@power(
    "m2857a2",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d4", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2857a2(c: Cast) -> None:
    """Poison for the enemies standing in it, and a mend for its own kind.

    "Each of these in the blast" is an `Ident.ref` and nothing else says it
    -- `c.is_kind` answers about type words, which several stat blocks
    share. The heal is rolled per creature, which is what a printed line
    naming dice for each of several targets means, and it is hung on
    `c.first` so the whole Effect line happens once rather than once per
    enemy caught.
    """
    if c.strike():
        c.hit()
    if not c.first:
        return
    for kin in c.in_squares(c.area()):
        if _same_row(c, kin, "m2857"):
            c.heal(c.roll("1d4") + 5, on=kin)


# --------------------------------------------------------------------------
# m2932
# --------------------------------------------------------------------------


@power(
    "m2932a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2932a0(c: Cast) -> None:
    _sapping_aura(c, 1, 2)


@power(
    "m2932a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 2),
)
def m2932a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2932a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d8", 3, kind=LIMITED, half_on_miss=True),
)
def m2932a2(c: Cast) -> None:
    """A step, and then everything within reach of where it lands.

    The row declares no target even though it is a burst: a header's targets
    are chosen before the body runs, so a burst rolled after a shift would
    catch whoever was standing round the square it *left*. The step is
    printed first and is the whole point of the row, so it is taken first
    and the burst is gathered afterwards. "Creatures in the burst" is both
    sides, which `side="other"` says and `EACH_ENEMY` does not.
    """
    c.shift(4)
    for who in sorted(c.within(1, side="other")):
        if c.strike(on=who):
            c.hit(on=who)
            c.push(1, on=who)
        else:
            c.hit(on=who, half=True)


# --------------------------------------------------------------------------
# m2961
# --------------------------------------------------------------------------


@power(
    "m2961a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m2961a0(c: Cast) -> None:
    """The step is on the hit line with the damage -- one printed clause --
    so it is taken only when the blow lands."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m2961a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires=_has_advantage,
    requires_text="the target must be granting combat advantage to the m2961",
)
def m2961a1(c: Cast) -> None:
    """Two swings into somebody who is not watching.

    The printed restriction is per target and the header's `target` field
    cannot say so: `requires` carries the half about the board, and the aim
    is narrowed here rather than refused, for the reason m297a2 gives -- a
    target line names the pool a power may be aimed into, so a caller
    handing it a creature the line does not allow is picking from the wrong
    list. The blade is the row that prints it rather than a copy, so its
    own step after each blow comes along, which is what the card says.
    """
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and has_combat_advantage(c.world, c.me, foe)
            ],
            "m2961a1: which creature",
        )
    if victim is None:
        return
    for _ in range(2):
        use(c.world, c.me, "m2961a0", targets=[victim], spend=False)


@power(
    "m2961a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m2961a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m2961a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2961a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it has no target, no
    attack and no moment at which it would be used."""
    _dodges_openings(c)


@power(
    "m2961a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m2961a4(c: Cast) -> None:
    """Flight for one turn, at whatever it can run.

    `c.mode` is the grant, because `movement.mode_of` picks the best mode a
    creature has and this one has no fly speed of its own. "And can hover"
    needs nothing said: `movement.settle` only puts a flyer down at the end
    of its turn, and the printed line runs out at exactly that moment.
    """
    c.mode("fly", c.speed_of(), until=When.EOT)


# --------------------------------------------------------------------------
# m2973
# --------------------------------------------------------------------------


@power(
    "m2973a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2973a0(c: Cast) -> None:
    """Five more on anybody the pack has closed around.

    A gated damage modifier rather than a watch on the hit: the damage
    context carries `target`, so the gate can count the neighbours at the
    moment the blow lands, and the printed line adds a flat number rather
    than dice. `c.allies()` never includes the caster, which is what the
    printed count of "its allies" means.
    """
    c.bonus(
        "damage",
        5,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: _mobbed(c, ctx.get("target"), 2),
    )


@power(
    "m2973a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m2973a1(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider on the
    first, so it is rolled in the body and the header keeps the printed one
    that rescales. Whether it is hurt is read before the swing, so a
    reaction that wounds it mid-attack does not change the number."""
    hurt = c.bloodied(on=c.me)
    if not c.strike():
        return
    if hurt:
        c.damage("2d6", 10)
    else:
        c.hit()
    c.ongoing(5)


@power(
    "m2973a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 10),
)
def m2973a2(c: Cast) -> None:
    """A step in, a blow, and a friend let off the leash.

    The printed line names its order outright -- "Before the attack, the
    gnoll shifts up to 2 squares" -- so the usual arrangement of swinging
    first is not taken here. The ally's step is a second Effect line and so
    happens whether or not the blow landed; the shove is on the hit line and
    is optional, which `c.may` asks.
    """
    hurt = c.bloodied(on=c.me)
    c.shift(2)
    if c.strike():
        if hurt:
            c.damage("1d10", 12)
        else:
            c.hit()
        if c.may("push the target 1 square"):
            c.push(1)
    mate = c.choose(
        [a for a in c.within(5, side="ally") if a != c.me],
        "m2973a2: which ally steps",
    )
    if mate is not None:
        c.shift(1, who=mate)


@power(
    "m2973a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m2973a3(c: Cast) -> None:
    """Every friend in earshot swings at once.

    `EACH_ALLY` includes the caster -- `candidates` puts the actor in its own
    ally pool -- and "allies in the burst" does not, so it is left out here.
    `c.grant_attack` with no `ref` rolls whatever that creature's own basic
    attack is, which for a monster is one of its own abilities.
    """
    friend = c.target
    if friend is None or friend == c.me:
        return
    beside = sorted(c.within(1, of=friend, side="enemy"))
    foe = c.choose(beside, "m2973a3: which enemy the ally swings at") if beside else None
    if foe is not None:
        c.grant_attack(friend, on=foe)


# --------------------------------------------------------------------------
# m3000
# --------------------------------------------------------------------------


@power(
    "m3000a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m3000a0(c: Cast) -> None:
    """Extra cold on anything it catches already labouring.

    Dice rather than a flat number, so it is rolled as the blow lands
    instead of riding along as a damage modifier -- and it is dealt as its
    own cold packet, which a resistance reads. `_reach_kind` asks the branch
    rather than the keywords, which is what "its melee attacks" means.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(ev) not in _MELEE_KINDS:
            return
        if is_(c.world, ev.target, Condition.SLOWED):
            c.damage("2d6", dtype=DamageType.COLD, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m3000a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m3000a1(c: Cast) -> None:
    """The cold is a second expression on the same hit, so it is rolled in the
    body and the header keeps the printed line that rescales."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)


@power(
    "m3000a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3000a2(c: Cast) -> None:
    """A pass on the wing: the swing is taken first, for the reason the levels
    below give on their rows of this shape -- the flight picks its own
    destination and one taken first can leave the target out of reach.
    Leaving provokes nothing from the creature it struck, which is the
    printed exemption."""
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m3000a1", targets=[c.target], spend=False)
    c.move(_fly_speed(c))


@power(
    "m3000a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.COLD),
)
def m3000a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m3010
# --------------------------------------------------------------------------


#: The label the crit range is kept under, so a second use of the row does
#: not stack a second copy of it.
_M3010_KEEN = "m3010a0 crit range"


@power(
    "m3010a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 5),
)
def m3010a0(c: Cast) -> None:
    """A wide critical, an opening bonus, and a burn.

    The crit range is printed on this attack line rather than as a trait, so
    it is installed from the body -- gated on this row's own ref, which the
    attack context carries as `power`, and guarded by its label so a second
    use does not stack a second point of it. 19-20 is one better than the
    ordinary 20, which is what the number means.

    Whether the blow had the drop is read off the roll that was just made:
    asking the board afterwards answers "no" for a creature that struck from
    concealment, and for a one-shot grant it has already been spent. The
    printed 6 for a critical is a flat number on top of the maxed dice.
    """
    me = c.me
    if not any(e.label == _M3010_KEEN for e in c.world.effects.of(me)):
        keen = c.bonus(
            "crit_range",
            1,
            until=When.ENCOUNTER,
            on=me,
            kind="untyped",
            when=lambda ctx: ctx.get("power") == "m3010a0",
        )
        if keen is not None:
            keen.label = _M3010_KEEN
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.damage("2d6")
    if c.crit:
        c.flat(6)
    c.ongoing(5)


@power(
    "m3010a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m3010a1(c: Cast) -> None:
    """Two swings with a step after each, in the printed order. The blade is
    the row that prints it rather than a copy, so the crit range, the
    opening bonus and the burn all come along with it."""
    for _ in range(2):
        use(c.world, c.me, "m3010a0", targets=[c.target], spend=False)
        c.shift(2)


@power(
    "m3010a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3010a2(c: Cast) -> None:
    """The waiver is handed back as soon as the step is over, so a second
    move on the same turn pays for rough ground the way it should."""
    sure = c.ignores_difficult(until=When.EOT)
    c.shift(4)
    if sure is not None:
        c.world.effects.end(sure, "the step is over")


# --------------------------------------------------------------------------
# m3083
# --------------------------------------------------------------------------


@power(
    "m3083a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3083a0(c: Cast) -> None:
    _dodges_openings(c)


@power(
    "m3083a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3083a1(c: Cast) -> None:
    """Nothing hurt or burning gets a swing at it on the way past.

    Not `c.no_provoke`, which waives the window for one named creature or
    for everybody: the printed line waives it for a *class* of creature and
    which ones those are changes every time anything takes damage. So the
    window is refused as it opens, which is the same seam `c.no_provoke`
    uses. `ev.actor` is whoever would swing and `ev.provoker` is whoever
    moved, which is the way round this line needs.
    """
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker != me:
            return
        if c.bloodied(on=ev.actor) or _taking_ongoing(c, ev.actor):
            ev.cancel("m3083a1")

    c.watch(
        OpportunityWindow,
        veto,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m3083a1",
    )


@power(
    "m3083a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3083a2(c: Cast) -> None:
    """A blade worked into a wound that is already open.

    Both halves are asked at the moment of the `Hit`: whether the target was
    caught out is read off the roll -- asking the board afterwards answers
    "no" for a blow struck from concealment -- and the burn is raised in
    place rather than a second one applied, because the printed line says
    the ongoing damage goes up and a second effect would be a second saving
    throw.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        burn = _worst_burn(c, ev.target)
        if burn is not None and burn.ongoing is not None:
            amount, dtype = burn.ongoing
            burn.ongoing = (amount + 5, dtype)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m3083a2")


@power(
    "m3083a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 3),
)
def m3083a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3083a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 3, kind=LIMITED),
)
def m3083a4(c: Cast) -> None:
    """"Recharge when first bloodied" on top of the die the database files.

    `_recharge_on` is the printed sentence and the header's 6 is the roll;
    the two only ever agree to make the row available sooner. Armed from the
    body, which is all that is needed -- the row has to have been spent
    before there is anything to give back -- and `Bloodied` is emitted on
    the crossing and nowhere else, so "first" needs no guard of its own.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.prone()
        c.slowed(until=When.EONT)
        c.ongoing(5)


@power(
    "m3083a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 3),
    requires=_a_prone_enemy,
    requires_text="the target must be prone",
)
def m3083a5(c: Cast) -> None:
    """A boot to somebody already on the floor.

    "One prone creature" is a restriction on the target and the header's
    `target` field cannot say so, so `requires` carries the half about the
    board and the aim is narrowed here.
    """
    victim = c.target
    if victim is None or not c.is_(Condition.PRONE, on=victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and c.is_(Condition.PRONE, on=foe)
            ],
            "m3083a5: which creature",
        )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(3, on=victim)


_M3083_FELLED = "the m3083 bloodies an enemy or drops one to 0 hit points"


def _felled_an_enemy(world: World, me: int, ev: DamageApplied) -> bool:
    """Did *this* creature just bloody or drop an enemy?

    `Bloodied` and `Dropped` name the creature that went down and nothing
    about who put it there, so neither can answer a printed line whose
    subject is the attacker. `DamageApplied` carries `source`, the hit
    points left and the size of the blow, which between them say both.

    The sides are compared with `team` rather than through `query.enemies`,
    which filters out the dead -- so a creature that has just been dropped
    is not in it and the test would be false exactly when it matters.
    """
    if ev.source != me or ev.amount <= 0 or ev.target == me:
        return False
    if team(world, ev.target) is team(world, me):
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return ev.hp <= 0 or (ev.hp <= half < ev.hp + ev.amount)


@power(
    "m3083a6",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3083_FELLED,
    on=Trigger(DamageApplied, when=_felled_an_enemy, text=_M3083_FELLED),
)
def m3083a6(c: Cast) -> None:
    """"Effect (No Action)" is a free action with a trigger, which is what
    `FREE` plus a declared `on=` is."""
    c.temp_hp(c.roll("1d8") + 2)


# --------------------------------------------------------------------------
# m387
# --------------------------------------------------------------------------


@power(
    "m387a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4),
)
def m387a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M387_SWUNG_AT = "an enemy makes an opportunity attack against the m387"


@power(
    "m387a1",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    trigger=_M387_SWUNG_AT,
    on=Trigger(
        AttackDeclared, when=both(targets_me, by_opportunity), text=_M387_SWUNG_AT
    ),
)
def m387a1(c: Cast) -> None:
    """Answered on the declaration, which is where `opportunity` is first
    carried and where the enemy that swung is named -- the dispatcher aims a
    single-enemy row at whoever the event was about, so no choosing is
    needed. The blade is the row that prints it rather than a copy."""
    if c.target is not None:
        use(c.world, c.me, "m387a0", targets=[c.target], spend=False)


@power(
    "m387a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m387a2(c: Cast) -> None:
    """An extra die for having covered ground, measured as the printed line
    measures it: where it ended against where the move began, not how many
    squares it walked. "On its turn" is a real clause -- being shoved four
    squares on somebody else's turn is not this -- so whose turn it is is
    asked as the move ends. Dice rather than a flat number, so it is rolled
    as the blow lands instead of riding along as a damage modifier."""
    me = c.me
    held: list[Effect] = []

    def rider(ev: Hit) -> None:
        if ev.attacker == me:
            c.damage("1d6", on=ev.target, detail="m387a2")

    def far_enough(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.watch(Hit, rider, until=When.SONT, on=me, label="m387a2 range"),
        )

    _after_moving(c, far_enough)


@power(
    "m387a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="the m387 must be bloodied",
)
def m387a3(c: Cast) -> None:
    """Faster and harder to hit for the rest of the fight, unless it goes down.

    "Or until rendered unconscious" is a duration the enum has no word for,
    so the three holds run to the end of the encounter and are ended by hand
    when the condition lands. `ConditionApplied` names its subject `target`,
    which is why the check is on `ev.target` -- `ev.actor` does not exist on
    it and reading it would make this silently dead.

    The printed Healing keyword is kept although the line restores nothing:
    it is what a leader's power reads to decide this is worth answering.
    """
    me = c.me
    holds = [
        c.bonus("speed", 2, until=When.ENCOUNTER, on=me, kind="untyped"),
        c.bonus(AC, 1, until=When.ENCOUNTER, on=me, kind="untyped"),
        c.bonus(REF, 1, until=When.ENCOUNTER, on=me, kind="untyped"),
    ]

    def collapse(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.UNCONSCIOUS:
            return
        for hold in holds:
            if hold is not None:
                c.world.effects.end(hold, "rendered unconscious")

    c.watch(
        ConditionApplied, collapse, until=When.ENCOUNTER, on=me, label="m387a3 ends"
    )


# --------------------------------------------------------------------------
# m401
# --------------------------------------------------------------------------


@power(
    "m401a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m401a0(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider on the
    first, so it is rolled in the body and the header keeps the printed one
    that rescales. Whether it had the drop is read off the roll that was just
    made, for the reason m429a0 gives."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("4d6", 8)
    else:
        c.hit()


@power(
    "m401a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m401a1(c: Cast) -> None:
    """The heavier line changes both halves of the expression -- more dice and
    a smaller number -- so it is rolled in the body outright."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("4d8", 4)
    else:
        c.hit()


@power(
    "m401a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m401a2(c: Cast) -> None:
    """Swing, step away, swing again -- the printed line names its own order
    and it is not the usual one, so it is kept.

    `c.basic` is what "a basic attack" names, whichever of its own rows that
    turns out to be. The second one picks a fresh target, because after
    three squares the creature it just struck is often no longer the one in
    reach.
    """
    c.basic(on=c.target)
    c.shift(3)
    beside = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    c.basic(on=beside[0] if beside else c.target)


@power(
    "m401a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m401a3(c: Cast) -> None:
    """No damage at all: an opening is the whole of the hit line.

    "Recharge when the m401 hits with a basic attack" is the printed
    sentence on top of the die the database files, and `_basic_ref` is which
    row that creature's basic attack actually is. The step is printed as
    "before or after the attack", which is a choice rather than two steps,
    so it is asked once and taken on whichever side the answer names.
    """
    me = c.me
    basic = _basic_ref(c)
    _recharge_on(c, Hit, lambda ev: ev.attacker == me and ev.power == basic)
    early = c.may("step before the attack")
    if early:
        c.shift(1)
    if c.strike():
        c.grants_advantage(until=When.EOT)
    if not early:
        c.shift(1)


# --------------------------------------------------------------------------
# m4780
# --------------------------------------------------------------------------


#: What the printed Requirement asks of whoever is in the saddle.
_M4780_RIDER_LEVEL = 7

#: The one-shot hold m4780a0 lays when the rider is swinging instead. Read
#: by m4780a2's caller, which is the only place the substitution can happen:
#: `PowerUsed` is announced before a body runs, so the trait cannot reach
#: into the row it modifies except by leaving something for it to find.
_M4780_INSTEAD = "m4780a0 in place of"


def _qualified_rider(c: Cast) -> int | None:
    """Whoever is in the saddle, if they are friendly and high enough."""
    rider = c.rider()
    if rider is None or team(c.world, rider) is not team(c.world, c.me):
        return None
    stats = c.world.get(rider, Stats)
    return rider if stats is not None and stats.level >= _M4780_RIDER_LEVEL else None


@power(
    "m4780a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="the m4780 must be carrying a friendly rider of 7th level or higher",
)
def m4780a0(c: Cast) -> None:
    """When it makes its flying pass, whoever is on its back swings instead.

    Hung on `PowerUsed` rather than written into m4780a3: that is a separate
    row and cannot reach this one. The announcement comes before the body,
    which is what makes the substitution possible at all -- the trait grants
    the rider's blow and leaves a one-shot hold, and m4780a3 finds the hold
    and forgoes its own.

    The spec prints the triggering row's id as one belonging to a different
    stat block, which this creature does not know and could never use; the
    row it plainly names -- its own flying pass, whose attack is the one
    being replaced -- is the one written.

    Only the basic attack is granted, for the reason m3071a3 gives: the
    printed alternative would need the rider's melee attack powers
    enumerated, and nothing can ask a creature that.
    """
    me = c.me

    def alongside(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != "m4780a3" or not ev.targets:
            return
        rider = _qualified_rider(c)
        if rider is None:
            return
        c.world.effects.apply(me, me, When.EOT, label=_M4780_INSTEAD)
        c.grant_attack(rider, on=ev.targets[0])

    c.watch(PowerUsed, alongside, until=When.ENCOUNTER, on=me, label="m4780a0")


@power(
    "m4780a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4780a1(c: Cast) -> None:
    """It takes its prisoner with it, and the prisoner gets no swing at it.

    Two halves, on two events. The waiver goes on as the grab lands and is
    hung on the relation rather than on a clock, since "while grabbed" is a
    duration the enum has no word for and a save-ends hold would let a
    creature shake off the exemption while still being held.

    The carry is done at the end of the move rather than step by step: the
    mount's whole path is walked inside one `MoveEnd`, and pulling the
    prisoner to a free square beside where it stopped is what "pulls with it"
    comes to. The grab itself is untouched, which is the printed "remains
    grabbed" -- a pull does not clear the relation.
    """
    me = c.me

    def seized(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.source != me:
            return
        guard = c.no_provoke(from_=ev.target, until=When.ENCOUNTER)
        _until_the_grab_ends(c, ev.target, guard)

    def carry(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        for held in list(c.world.relations.targets(Relation.GRABBED_BY, me)):
            gap = distance_between(c.world, me, held)
            if gap <= 1:
                continue
            spot = _free_square_beside(c, me)
            if spot is not None:
                c.pull(gap, on=held, to=spot)

    c.watch(RelationSet, seized, until=When.ENCOUNTER, on=me, label="m4780a1 grab")
    c.watch(MoveEnd, carry, until=When.ENCOUNTER, on=me, label="m4780a1 carry")


@power(
    "m4780a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m4780a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4780a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4780a3(c: Cast) -> None:
    """A pass on the wing, with the swing taken first for the reason the
    levels below give. If m4780a0 has left its hold, the rider has already
    swung in place of this and the hold is spent here."""
    instead = next(
        (e for e in c.world.effects.of(c.me) if e.label == _M4780_INSTEAD), None
    )
    c.no_provoke(from_=c.target)
    if instead is not None:
        c.world.effects.end(instead, "the rider swung instead")
    else:
        use(c.world, c.me, "m4780a2", targets=[c.target], spend=False)
    c.move(_fly_speed(c))


@power(
    "m4780a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_flying,
    requires_text="the m4780 must be flying",
)
def m4780a4(c: Cast) -> None:
    """The same pass, and whatever it catches is carried off.

    The Requirement is about what the creature is *doing*, which is what
    `Movement.using` holds and what `_flying` reads; having a fly speed is a
    different question and is not this one.

    The hit belongs to the row two levels down, so it is watched for under
    that ref rather than under this one -- `use` says a row went off and
    never says it landed. The spec prints the inner row's id as one
    belonging to a different stat block; the flying pass is the row it
    plainly names, and is the one used.
    """
    victim = c.target
    if victim is None:
        return
    caught = _while_watching(
        c,
        "m4780a2",
        lambda: use(c.world, c.me, "m4780a3", targets=[victim], spend=False),
    )
    for who in caught:
        c.grab(on=who)


# --------------------------------------------------------------------------
# m4882
# --------------------------------------------------------------------------


@power(
    "m4882a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4882a0(c: Cast) -> None:
    """A Stealth bonus against a passive number, and nothing else -- there are
    no skill checks in the engine and no combat consequence to invent, so it
    is declared inert rather than approximated."""
    c.note("m4882a0: +10 to Stealth against an enemy's passive Perception")


@power(
    "m4882a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m4882a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4882a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4882a2(c: Cast) -> None:
    """Four squares, two swings, and two different creatures.

    The four are spent two at a time between the swings rather than all at
    once, because "at any point during the shift" is what makes two separate
    targets reachable and a single step to one destination is not. The row
    declares no targets: the route decides whom it catches, and the set of
    who has already been swung at is the printed "two different targets".
    """
    struck: set[int] = set()
    for _ in range(2):
        c.shift(2)
        victim = next(
            (
                foe
                for foe in c.enemies()
                if foe not in struck and distance_between(c.world, c.me, foe) <= 1
            ),
            None,
        )
        if victim is None:
            continue
        struck.add(victim)
        for who in _struck(c, "m4882a1", 1, victim):
            c.slide(1, on=who)
            c.prone(on=who)


@power(
    "m4882a3",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4882a3(c: Cast) -> None:
    """"Without provoking opportunity attacks" is the whole of what the
    printed line adds; the flight is an ordinary move, which
    `movement.mode_of` already takes on the wing."""
    _guarded_move(c, 4)


# --------------------------------------------------------------------------
# m5009
# --------------------------------------------------------------------------


@power(
    "m5009a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m5009a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5009a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 7),
)
def m5009a1(c: Cast) -> None:
    """A printed range of "10/20" takes the normal range, which is what the
    levels below settled."""
    if c.strike():
        c.hit()


@power(
    "m5009a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 5),
)
def m5009a2(c: Cast) -> None:
    """The swing is taken first, for the reason the levels below give: the
    walk picks its own destination and one taken first can leave the target
    out of reach. The attack is this row's own line rather than another
    row's, so it is `c.strike` here."""
    if c.strike():
        c.hit()
    c.move(c.speed_of())


@power(
    "m5009a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5009a3(c: Cast) -> None:
    """A jump is a move in the engine -- there is no separate op -- so "this
    movement does not provoke opportunity attacks" is the whole of what the
    printed line adds."""
    _guarded_move(c, c.speed_of())


_M5009_STRUCK = "the m5009 is hit by an attack"


@power(
    "m5009a4",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5009_STRUCK,
    on=Trigger(
        DamageApplied, when=both(targets_me, _hurt_by_an_attack), text=_M5009_STRUCK
    ),
)
def m5009a4(c: Cast) -> None:
    """Declared on the damage rather than on the `Hit`, which is the printed
    trigger but the wrong moment: `resolve.attack` announces the hit
    *before* the body deals its damage, so a reaction hung there is asked
    "did that blow bloody you?" one beat before the blow has landed. The
    damage event is emitted after the hit points have come off and before
    `Bloodied`, which is exactly where this question has an answer. An
    attack that lands and deals nothing at all is the one case the two
    readings differ on."""
    c.shift(4 if c.bloodied(on=c.me) else 1)


_M5009_LANDED = "the m5009 hits with m5009a0 or m5009a1"


def _with_either_weapon(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power in ("m5009a0", "m5009a1")


@power(
    "m5009a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    trigger=_M5009_LANDED,
    on=Trigger(Hit, when=_with_either_weapon, text=_M5009_LANDED),
)
def m5009a5(c: Cast) -> None:
    """The printed trigger names two weapons, which are the two rows that are
    nothing but a weapon attack; the third row carrying the same keyword
    prints its own damage line and is not one of them.

    The extra dice go to whoever the triggering attack hit, and are dealt as
    their own packet rather than folded into the blow -- which is how every
    other rider in the tree shows in the log.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("2d6", dtype=DamageType.PSYCHIC, on=victim)


# --------------------------------------------------------------------------
# m810
# --------------------------------------------------------------------------


@power(
    "m810a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 2),
)
def m810a0(c: Cast) -> None:
    """The bracketed +14 is the same attack two better against a target that
    is already hurt, so it is `plus=` on the roll rather than a second
    printed line. The necrotic is a flat number on its own packet, which a
    resistance reads."""
    if c.strike(plus=2 if c.bloodied() else 0):
        c.hit()
        c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m810a1",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m810a1(c: Cast) -> None:
    c.shift(2 if c.bloodied(on=c.me) else 1)
