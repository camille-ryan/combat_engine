"""Monster abilities, level 9: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=14)` and `Damage("3d6", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the eight levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; a stat block printing no range at all means melee 1; and a
helper written for an earlier level is imported rather than copied.

Five things this file had to settle.

**Two bonuses of the same kind do not add.** `Mods.total` takes the larger of
two bonuses sharing a `kind`, which is the printed stacking rule -- so "+2
with one creature adjacent, +4 with two or more" is a +2 and a gated **+4**,
not a +2 and a second +2. Written the second way it comes to +2 forever and
reads exactly like a working trait. m487a0's aura pays a penalty to one side
and a bonus to the other, which is two different `what`s and stacks fine.

**Regeneration that can be switched off** is a `TurnStart` watch plus a named
hold, the arrangement level 8 settled on. "Has at least 1 hit point" is
`hp > 0` rather than `alive`: the printed sentence is about not knitting
itself back together once it is down.

**Not dying** is answered on the creature's own `Dropped`. `_check_down`
re-reads hit points after the emit, so a row that heals itself inside that
window really does stay up -- and a second `Dropped` while it is already down
is how the acid-or-fire clause kills it, because that is the only reading
under which an ordinary blow landing on the body does not.

**"Uses this attack twice, and if both hit the same target ..."** cannot be
read off `use`, which reports whether the row could be used and not whether
it landed. The hits are counted off the bus for as long as the row is
swinging, which is `_twice` below and level 8's arrangement.

**Being removed from play** is `Condition.REMOVED`: on the board, out of the
fight. The way back is hung on that effect's own ending rather than on a
clock, because "when the target saves, it reappears" is what the printed line
measures.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _aura,
    _has_hold,
    _holding,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Position,
    Powers,
    Relation,
    Size,
    Square,
    Stats,
    UpTo,
    Usage,
    When,
    World,
    distance,
    footprint,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    DamageApplied,
    Dropped,
    Event,
    RelationCleared,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, flanked_by, squares
from combat_engine.engine.triggers import Trigger, about_me

#: The two damage types a troll's regeneration and its refusal to die both
#: answer to. Kept as one tuple because the stat block prints the same pair
#: in three separate sentences.
CAUTERISING = (DamageType.ACID, DamageType.FIRE)


def _regenerates(c: Cast, amount: int, doused: str = "") -> None:
    """Regeneration, written out: the engine holds no such thing.

    "Whenever it starts its turn and has at least 1 hit point" is `hp > 0`
    and not `alive` -- the printed sentence says it does not knit itself back
    together once it is down. `doused` names a hold that switches it off for
    a turn, for the stat blocks that print one.
    """
    me = c.me

    def regenerate(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is None or health.hp <= 0:
            return
        if doused and any(eff.label == doused for eff in c.world.effects.of(me)):
            return
        c.heal(amount, on=me)

    c.watch(TurnStart, regenerate, until=When.ENCOUNTER, on=me, label=c.ref)


def _dealt(world: World, ev: Event, victim: int, types: tuple[DamageType, ...]) -> bool:
    """Was the blow that caused this `Dropped` one of those types?

    `Dropped` names only who fell. The wound is the nearest earlier
    `DamageApplied` on that creature, which is the same place level 8 reads
    attribution from and the only place either exists.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            return past.dtype in types
    return False


def _volley(c: Cast, ref: str, who: int) -> bool:
    """Swing the row that prints the attack, and say whether `who` took both.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is hit twice --
    which is the only reading that loses nothing, and the only one under
    which "if both attacks hit the same target" can ever be true.

    "Both hit" cannot be read off `use`, which reports whether the row could
    be used and not whether it landed, so the hits are counted off the bus
    for as long as this row is swinging.
    """
    me = c.me
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == ref:
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        for _ in range(2 if c.first and c.last else 1):
            if not alive(c.world, who):
                break
            use(c.world, me, ref, targets=[who], spend=False)
    finally:
        c.world.effects.end(counter, "the attacks are done")
    return landed.count(who) >= 2


def _put_beside(c: Cast, who: int, anchor: int) -> bool:
    """Set that creature down in a free square next to this one.

    `_free_squares_near` a level below measures the *caster's* footprint,
    and the creature being moved here is somebody else -- a Large body
    offered a square a Medium one fits in simply does not arrive.
    """
    here = c.world.get(who, Position)
    size = here.size if here is not None else Size.MEDIUM
    free = sorted(
        sq
        for sq in spread(squares(c.world, anchor), 1)
        if all(
            c.world.grid.passable(part)
            and c.world.grid.occupant(part) in (None, who)
            for part in footprint(sq, size)
        )
    )
    if not free:
        return False
    where = c.world.decide(c.me, "teleport", free, f"{c.ref}: where it reappears")
    span = max((distance(sq, where) for sq in squares(c.world, who)), default=1)
    return c.teleport(span, who=who, to=where)


# ==========================================================================
# m251
# ==========================================================================


@power(
    "m251a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m251a0(c: Cast) -> None:
    """The grab and the burn are two separate printed durations -- "until
    escape" and "save ends" -- so they are two effects rather than one
    carrying both."""
    if c.strike():
        c.hit()
        c.grab()
        c.ongoing(5)


@power(
    "m251a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    damage=Damage("1d8", 5),
    requires=_has_hold,
    requires_text="the m251 must have a creature grabbed",
)
def m251a1(c: Cast) -> None:
    """No attack roll is printed: it already has hold of the thing. The
    printed target is "a creature grabbed by the m251", which no `Target` can
    say, so the header takes one enemy and the body aims at whoever is
    actually being held."""
    held = _holding(c.world, c.me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None:
        c.hit(on=victim)


@power(
    "m251a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m251a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Who it is flanking changes every time anybody moves, so this is a gated
    modifier asked as the roll is made rather than a bonus put on and taken
    off. The gate reads `target` off the attack context, which is the only
    place the creature being swung at appears.
    """
    me = c.me

    def flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, me)

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=flanking)


@power(
    "m251a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m251a3(c: Cast) -> None:
    """The bonus is the allies' to spend, so it rides on each of them and is
    gated on who they are swinging at -- a modifier is read off the attacker,
    and one held on the m251 would never be consulted.

    Whoever is on its side when the trait arms is who gets it. An ally that
    arrives later is not covered, which is the price of a modifier being a
    thing a creature carries.
    """
    me = c.me

    def its_prisoner(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in _holding(c.world, me)

    for friend in sorted(c.allies()):
        if friend != me:
            c.bonus("attack", 2, until=When.ENCOUNTER, on=friend, when=its_prisoner)


# ==========================================================================
# m412
# ==========================================================================


#: The hold that says a creature is inside this one. Read by the printed
#: Requirement on m412a2, which counts them.
_M412_INSIDE = "m412a2 taken"


def _room_inside(world: World, eid: int) -> bool:
    return (
        sum(
            1
            for eff in world.effects.live.values()
            if eff.source == eid and eff.label == _M412_INSIDE and not eff.ended
        )
        < 2
    )


@power(
    "m412a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m412a0(c: Cast) -> None:
    """Regeneration with nothing that switches it off, unlike the two stat
    blocks that print a damage type beside it."""
    _regenerates(c, 5)


@power(
    "m412a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m412a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m412a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=12),
    requires=_room_inside,
    requires_text="the m412 must not have two creatures removed from play",
)
def m412a2(c: Cast) -> None:
    """Two swings of the row that prints them, and a secondary attack on the
    creature that took both.

    The header carries the secondary line rather than the two it opens with:
    that is the one roll this row makes for itself, and the card should print
    it. No damage beside it at all -- being swallowed is the whole of the hit.

    "Pulls the target into its space" is written as a pull as far as the
    creature will come rather than a share of the square, because the next
    clause takes it off the board entirely and a shared footprint would only
    have to be undone. The way back out is hung on the hold's own ending,
    which is what "when the target saves, it reappears" measures, and the
    square is chosen then rather than now.
    """
    me, victim = c.me, c.target
    if victim is None or not _volley(c, "m412a1", victim):
        return
    if not c.strike(on=victim):
        return
    c.pull(max(1, c.distance(victim)), on=victim)
    inside = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=_M412_INSIDE,
        conditions=(Condition.REMOVED,),
    )

    def digest(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or inside.ended:
            return
        c.flat(10, on=victim)
        c.heal(10, on=me)

    inside.subs.append(c.world.bus.on(TurnStart, digest, owner=me))
    inside.on_end.append(lambda: _put_beside(c, victim, me))


_M412_SHOCKED = "a lightning effect deals damage to the m412"


def _lightning_on_me(world: World, me: int, ev: DamageApplied) -> bool:
    """The printed trigger reads "deals damage", and this creature is immune
    to lightning -- so read literally the row could never fire on the stat
    block that prints it. The arrival of the damage is what is answered,
    which is plainly what drinking a lightning bolt means."""
    return ev.target == me and ev.dtype is DamageType.LIGHTNING


@power(
    "m412a3",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M412_SHOCKED,
    on=Trigger(DamageApplied, when=_lightning_on_me, text=_M412_SHOCKED),
)
def m412a3(c: Cast) -> None:
    c.heal(10, on=c.me)


# ==========================================================================
# m47
# ==========================================================================


@power(
    "m47a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m47a0(c: Cast) -> None:
    """Two expressions on one line and the header holds one, so the untyped
    half stays in the header and the cold is rolled here.

    The opportunity die is rolled rather than added flat: a critical maxes
    every die of the attack, and `c.damage` is what honours that.
    """
    if not c.strike():
        return
    c.hit()
    c.damage("1d10", dtype=DamageType.COLD)
    if c.opportunity:
        c.damage("1d10", dtype=DamageType.COLD)


@power(
    "m47a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m47a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m47a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m47a2(c: Cast) -> None:
    """The spec prints the second row's id as one belonging to a stat block
    this creature is not; the row it plainly names is this one's own claw,
    which is what is used twice."""
    victim = c.target
    if victim is None:
        return
    if _volley(c, "m47a1", victim) and alive(c.world, victim):
        use(c.world, c.me, "m47a0", targets=[victim], spend=False)


@power(
    "m47a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("4d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m47a3(c: Cast) -> None:
    """"Slowed and weakened (save ends both)" is one effect carrying both
    conditions: applied separately the victim gets two saving throws and can
    shake off half of a thing the card prints as one."""
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS)


_M47_BLED = "the m47 is first bloodied"


@power(
    "m47a4",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger=_M47_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M47_BLED),
)
def m47a4(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.

    The spec prints the recharging row's id as one belonging to a different
    stat block, whose breath this creature does not know and could never
    use. The row it plainly names is this one's own recharge blast.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m47a3")
    use(c.world, c.me, "m47a3")


@power(
    "m47a5",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
)
def m47a5(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the condition.

    An aftereffect is what follows when the first hold ends, whichever way it
    ended, so it hangs off that hold rather than being applied alongside it --
    and not on `escalate`, which runs on a *failed* save and would never run
    at all for a hold on a turn clock.
    """
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m4805
# ==========================================================================


@power(
    "m4805a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4805a0(c: Cast) -> None:
    """The bonus is the rider's, so it rides on the rider and comes off when
    it dismounts. Whoever is already in the saddle is caught at the end: the
    relation may well have been set before the trait armed.

    "Of 9th level or higher" is asked once, as somebody mounts, because a
    creature does not gain levels mid-fight.
    """
    me = c.me
    held: dict[int, list[Effect]] = {}

    def mount_up(who: int) -> None:
        stats = c.world.get(who, Stats)
        if who in held or stats is None or stats.level < 9:
            return
        held[who] = [
            eff
            for eff in (
                c.bonus(AC, 1, until=When.ENCOUNTER, on=who),
                c.bonus(REF, 1, until=When.ENCOUNTER, on=who),
            )
            if eff is not None
        ]

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            mount_up(ev.target)

    def dismounted(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.RIDDEN_BY or ev.source != me:
            return
        for eff in held.pop(ev.target, []):
            c.world.effects.end(eff, "dismounted")

    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label=f"{c.ref} on")
    c.watch(RelationCleared, dismounted, until=When.ENCOUNTER, on=me, label=f"{c.ref} off")
    rider = c.rider()
    if rider is not None:
        mount_up(rider)


@power(
    "m4805a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d10", 5),
)
def m4805a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4805a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4805a2(c: Cast) -> None:
    """Nothing rides on whether both landed here, but the two swings are the
    same shape as the two stat blocks above, so they go the same way."""
    if c.target is not None:
        _volley(c, "m4805a1", c.target)


@power(
    "m4805a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4805a3(c: Cast) -> None:
    """Walking through whoever is in the way is `c.overrun`, which is the
    only thing that reports who was trampled -- and who was trampled is
    exactly what the printed line attacks.

    It is a trample rather than a shift, so the waiver is written beside it:
    a shift provokes nothing, and `c.no_provoke` with no creature named
    covers the whole move. The destination is chosen within twice its speed,
    which the trample itself would not have reached.
    """
    me = c.me
    reach = c.world.reachable_squares(me, c.speed_of() * 2)
    if not reach:
        return
    here = squares(c.world, me)
    foes = sorted(c.enemies())

    def in_the_way(dest: Square) -> int:
        """How many enemies the straight line to there goes through.

        `c.overrun` walks the line from here to the destination, so who gets
        trampled is settled entirely by which square is picked -- and offered
        in plain sorted order the answer with no decider installed is the
        lowest corner of the board, which tramples nobody. The count is
        measured without reaching into the mover's private line-drawer: a
        creature is on the way when the two legs add up to the whole.
        """
        span = min(distance(sq, dest) for sq in here)
        return sum(
            1
            for foe in foes
            if any(
                min(distance(sq, f) for sq in here) + distance(f, dest) == span
                for f in squares(c.world, foe)
            )
        )

    c.no_provoke(until=When.EOT)
    lines = sorted(reach, key=lambda sq: (-in_the_way(sq), sq))
    where = c.world.decide(me, "overrun", lines, f"{c.ref}: trample to")
    for victim in c.overrun(to=where):
        if victim in foes:
            use(c.world, me, "m4805a1", targets=[victim], spend=False)


# ==========================================================================
# m487
# ==========================================================================


@power(
    "m487a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m487a0(c: Cast) -> None:
    """One aura paying two different things, which is one ring for the board
    to draw rather than two laid on top of each other.

    A penalty and a bonus are different `what`s and never contend; the side
    an occupant is on decides which it gets, asked as it walks in. The m487
    is not its own ally, so it is left out of both.
    """
    me = c.me
    foes = set(c.enemies())

    def pay(who: int) -> Effect | None:
        if who in foes:
            return c.penalty("attack", 1, until=When.ENCOUNTER, on=who)
        return c.bonus("attack", 1, until=When.ENCOUNTER, on=who, kind="power")

    _aura(c, 3, lambda who: who != me, pay)


@power(
    "m487a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5),
)
def m487a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m723
# ==========================================================================


#: The hold that switches the regeneration off, and the hold that says the
#: creature is lying there waiting to get up. Both are read a turn after they
#: are laid, so they are named effects rather than closure variables.
_M723_DOUSED = "m723a0 doused"
_M723_DOWN = "m723a1 down"


@power(
    "m723a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m723a0(c: Cast) -> None:
    """The switch is on the source's own clock, so a burn taken now is still
    switching the regeneration off when its next turn begins."""
    me = c.me
    _regenerates(c, 5, _M723_DOUSED)

    def douse(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype in CAUTERISING and ev.amount > 0:
            c.effect(_M723_DOUSED, until=When.EONT, on=me)

    c.watch(DamageApplied, douse, until=When.ENCOUNTER, on=me, label=f"{c.ref} doused")


@power(
    "m723a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m723a1(c: Cast) -> None:
    """Refusing to die, answered on its own `Dropped`.

    `_check_down` re-reads hit points after the emit, which is what makes a
    row that heals itself inside that window actually stay up -- so one hit
    point is put back and the body is held unconscious until the start of its
    next turn, when it gets up with fifteen.

    An ordinary blow landing on the body drops it again, and the second
    `Dropped` puts the hit point back without laying a second hold: it stays
    down and still gets up. Acid or fire is the clause that kills, and it
    kills by this watch declining to catch it -- which is the only reading
    under which "it does not return to life in this way" and "an ordinary
    attack does not stop it" are both true.
    """
    me = c.me

    def get_up() -> None:
        health = c.world.get(me, Health)
        if health is not None and alive(c.world, me) and health.hp < 15:
            c.heal(15 - health.hp, on=me)

    def falls(ev: Dropped) -> None:
        if ev.actor != me or _dealt(c.world, ev, me, CAUTERISING):
            return
        c.heal(1, on=me)
        if any(eff.label == _M723_DOWN for eff in c.world.effects.of(me)):
            return
        hold = c.world.effects.apply(
            me, me, When.SONT, label=_M723_DOWN,
            conditions=(Condition.UNCONSCIOUS,),
        )
        hold.on_end.append(get_up)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m723a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 7),
)
def m723a2(c: Cast) -> None:
    """The second swing is the row's own declared line rolled again, not the
    row used again: a charge or a rider reaching back through `use` is
    refused, because the row is already in flight.

    Bloodying is a crossing, so it happens at most once per creature and the
    repeat cannot run away with itself.
    """
    victim = c.target
    if victim is None:
        return
    before = c.bloodied(victim)
    if not c.strike():
        return
    c.hit()
    if before or not c.bloodied(victim) or not alive(c.world, victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)


# ==========================================================================
# m92
# ==========================================================================


@power(
    "m92a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 7),
)
def m92a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m92a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 7, kind=LIMITED),
)
def m92a1(c: Cast) -> None:
    """"Medium size or smaller" is asked of the victim rather than of the
    blow, which is what `SMALL_ENOUGH` a level below enumerates."""
    if not c.strike():
        return
    c.hit()
    if c.size_of() in SMALL_ENOUGH:
        c.prone()


_M92_BLED = "the m92 is first bloodied"


@power(
    "m92a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 7, kind=LIMITED),
    trigger=_M92_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M92_BLED),
)
def m92a2(c: Cast) -> None:
    """A triggered burst picks its own targets: the dispatcher only aims a
    row that takes a single enemy, which this does not."""
    if c.strike():
        c.hit()
        c.ongoing(5)
