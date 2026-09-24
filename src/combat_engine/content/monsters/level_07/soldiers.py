"""Monster abilities, level 7: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=12)` and `Damage("2d8", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Several rows here are printed under an action heading and are plainly
traits; those are declared `ActionType.NONE` and armed once when the fight
starts. A printed range of "20/40" takes the short range, which is what the
creature can actually shoot without a penalty the engine does not model.

Two shapes recur at this tier and are written once at the top: an aura whose
occupants carry a hold while they are inside it, and the question of whom a
creature currently has hold of, which four of these stat blocks ask.

Two rows here -- m2890a5 and m494a6 -- are filed naming a ref that belongs
to no stat block in the tree. That is a cross-reference the database lost,
and each is written against the only recharging attack its own creature has.
See the docstrings and the report.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Initiative,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    Relation,
    Size,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.components import Budget
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageRolled,
    EffectExpired,
    EnterSquare,
    Event,
    ForcedMove,
    Hit,
    LeaveSquare,
    Miss,
    MoveStart,
    PowerUsed,
    RelationCleared,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import spread
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    enemies,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    by_melee,
)

#: What a printed "living creature" rules out. The engine holds no flag for
#: being alive, so the question is put to the type line the way `c.is_kind`
#: reads it.
LIFELESS = ("undead", "construct")

#: Sizes a printed "Medium size or smaller" covers.
SMALL_ENOUGH = (Size.TINY, Size.SMALL, Size.MEDIUM)

#: Moves that never open an opportunity window, copied from `movement._SAFE`
#: rather than imported: it is that module's private business, and a row
#: extending the reach of the window has to agree with it about which moves
#: open one at all.
SAFE_MOVES = ("shift", "teleport", "push", "pull", "slide", "place")

#: What ending a turn shakes off, for the rows that say so.
SHAKEN_OFF = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)

#: What would stop the extra attack, and ends instead of stopping it.
HELD_FAST = (Condition.STUNNED, Condition.DOMINATED)


def _living(c: Cast, who: int) -> bool:
    return not any(c.is_kind(word, on=who) for word in LIFELESS)


def _holding(c: Cast) -> list[int]:
    """Whoever this creature has hold of."""
    return list(c.world.relations.targets(Relation.GRABBED_BY, c.me))


def _has_hold(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _hands_free(world: World, eid: int) -> bool:
    """A printed Requirement of "must not be grabbing a creature"."""
    return not _has_hold(world, eid)


def _is_mounted(world: World, eid: int) -> bool:
    """A printed Requirement of "usable only while mounted".

    `Relation.RIDDEN_BY` runs mount to rider, so being *in* a saddle is
    having a source rather than a target -- the opposite of `c.rider()`.
    """
    return bool(world.relations.sources(Relation.RIDDEN_BY, eid))


def _aura(
    c: Cast,
    radius: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
) -> int:
    """An aura whose occupants carry a hold for as long as they are inside.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the hold should go on and
    come off. Whoever is already standing inside is caught at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(radius, until=When.ENCOUNTER)

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        take(actor)
    return ring


def _recharge_on(c: Cast, event: type[Event], test: Callable[[Any], bool]) -> None:
    """Put this row back up when its printed line says so, not only on a die.

    The database files a plain 6+ where the stat block prints "Recharge when
    ...". The number stays in the header, because that is what
    `actions.recharge` rolls and what the card shows; this is the printed
    sentence on top of it, and the two only ever agree to make the row
    available sooner.
    """
    ref, me = c.ref, c.me
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def back(ev: Event) -> None:
        known = c.world.get(me, Powers)
        if known is not None and test(ev):
            known.restore(ref)

    c.watch(event, back, until=When.ENCOUNTER, on=me, label=label)


def _until_that_blow_lands(c: Cast, attacker: int, guard: Effect | None) -> None:
    """End a hold as soon as that creature's blow has hit or missed.

    "A +3 bonus to AC **against that attack**" is not a duration, and it
    cannot be `c.bonus(once=True)` either: that spends itself on
    `AttackRolled`, and the defence is read *again* after that event is
    announced -- so the bonus would have been gone by the comparison it
    exists for. `Hit` and `Miss` are both after the comparison, which is the
    first moment there is nothing left for it to do.
    """
    if guard is None:
        return
    me = c.me

    def done(ev: Any) -> None:
        if ev.attacker == attacker and ev.target == me:
            c.world.effects.end(guard, "the attack is over")

    c.watch(Hit, done, until=When.EOT, on=me, label=f"{c.ref} struck")
    c.watch(Miss, done, until=When.EOT, on=me, label=f"{c.ref} missed")


# ==========================================================================
# m108
# ==========================================================================


@power(
    "m108a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d4", 5),
)
def m108a0(c: Cast) -> None:
    """The burning and the hold are one printed effect -- "save ends both" --
    so they hang on one `c.condition` with its `ongoing`, and not on two: two
    would be two saving throws against a thing the card says is one.

    The failed saves are a chain of `escalate`, each step ending the one
    before it and carrying the poison forward, so the victim never holds two
    of these. The condition is *replaced* rather than added to, which is what
    "immobilized instead of slowed" says.

    The miss line is a shorter hold on the m108's own clock -- a different
    duration, not a weaker version of the same one.
    """
    venom = (5, DamageType.POISON)

    def stun(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.STUNNED, until=When.SAVE_ENDS, on=eff.owner, ongoing=venom
        )

    def pin(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            on=eff.owner,
            ongoing=venom,
            escalate=stun,
        )

    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=venom, escalate=pin)
    else:
        c.slowed(until=When.EONT)


@power(
    "m108a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4),
)
def m108a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m177
# ==========================================================================


@power(
    "m177a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m177a0(c: Cast) -> None:
    """An aura 5, with the widened critical range held per occupant.

    "19-20" is one face more than the ordinary 20, which is exactly what
    `crit_range` counts. The printed line is about its allies, so the caster
    is dropped -- the `ally` pool puts it in -- and only the fey among them
    qualify.
    """
    me = c.me
    _aura(
        c,
        5,
        lambda who: who != me and who in c.allies() and c.is_kind("fey", on=who),
        lambda who: c.bonus("crit_range", 1, until=When.ENCOUNTER, on=who),
    )


@power(
    "m177a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m177a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m177a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 8, kind=LIMITED),
)
def m177a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m177a3",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m177a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m177a4",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
)
def m177a4(c: Cast) -> None:
    """A mark that burns whoever looks away, and lasts the fight.

    "Or until the m177 uses this power again" is the previous mark ended by
    hand, together with the two watches it carried -- all three are labelled
    off this ref, so one sweep takes the set.

    Whether the enemy attacked the m177 is answered off `PowerUsed` rather
    than off each `AttackDeclared`: an attack is announced once per target,
    so a burst that caught the m177 would have read as several attacks, most
    of which left it out. `PowerUsed` fires once per use and carries the
    whole target list, which is the printed question.
    """
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and eff.label.startswith(ref):
            c.world.effects.end(eff, "the m177 used it again")
    swung = [False]

    def noticed(ev: PowerUsed) -> None:
        p = get(ev.power)
        if ev.actor == victim and p is not None and p.is_attack and me in ev.targets:
            swung[0] = True

    def ignored(ev: TurnEnd) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if not swung[0]:
            c.flat(4, dtype=DamageType.RADIANT, on=victim)
        swung[0] = False

    hold = c.mark(until=When.ENCOUNTER, on=victim)
    seen = c.watch(PowerUsed, noticed, until=When.ENCOUNTER, on=me, label=f"{ref} watched")
    burn = c.watch(TurnEnd, ignored, until=When.ENCOUNTER, on=me, label=f"{ref} burn")
    if hold is not None:
        hold.on_end.append(lambda: c.world.effects.end(seen, "the mark ended"))
        hold.on_end.append(lambda: c.world.effects.end(burn, "the mark ended"))


_M177_STRUCK = "an attack damages an ally within 5 squares of the m177"


def _ally_is_struck(world: World, me: int, ev: DamageRolled) -> bool:
    """Damage from an *attack*, landing on somebody on this creature's side.

    `DamageRolled` carries the row that dealt it in `detail`, which is the
    only thing that tells an attack from ongoing damage or a zone -- both of
    which also roll damage and neither of which the printed trigger names.
    """
    who = ev.target
    if who == me or team(world, who) is not team(world, me):
        return False
    p = get(ev.detail or "")
    return p is not None and p.is_attack and distance_between(world, me, who) <= 5


@power(
    "m177a5",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M177_STRUCK,
    on=Trigger(DamageRolled, when=_ally_is_struck, text=_M177_STRUCK),
)
def m177a5(c: Cast) -> None:
    """Half the blow, taken off the ally and put onto the m177.

    Not `c.absorb`, which moves the *whole* of it: the printed line splits
    the damage rather than transferring it, so the event's own amount is
    halved in place -- an interrupt is the window in which it is still a
    proposal -- and the same number is dealt here.

    Declared with no target: the dispatcher aims a triggered row at whoever
    the event names, and here that is the ally, which is not who the
    m177 is doing this to.
    """
    ev = c.trigger
    whole = max(0, getattr(ev, "amount", 0))
    if whole <= 0:
        return
    share = whole // 2
    ev.amount = share
    c.flat(share, dtype=ev.dtype, on=c.me)


# ==========================================================================
# m249
# ==========================================================================


@power(
    "m249a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m249a0(c: Cast) -> None:
    """Whether it has hold of anybody changes with every escape, so the gate
    is read at the moment the defence is, rather than stored."""
    me = c.me

    def gripping(_ctx: dict[str, Any]) -> bool:
        foes = c.enemies()
        return any(who in foes for who in _holding(c))

    c.bonus(Defense.AC, 2, until=When.ENCOUNTER, on=me, when=gripping)


@power(
    "m249a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m249a1(c: Cast) -> None:
    """The hold and the penalty are one effect with one saving throw, as
    printed: "save ends both". `c.slowed` and `c.penalty` would have been
    two, and the target would have shrugged off half of it at a time."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.SLOWED,),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "m249a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 6),
    requires=_hands_free,
    requires_text="the m249 must not be grabbing a creature",
)
def m249a2(c: Cast) -> None:
    """The escape DC is not written: the engine has no contest to put it in,
    and a grab is ended by the escape rules rather than by a number on the
    row that made it."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m249a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m249a3(c: Cast) -> None:
    """Two swings, through the rows that print them, so their damage lines
    stay in one place.

    Which pair is a real choice and is offered as one -- but m249a2 is shut
    whenever the m249 already has hold of somebody, and then the second
    printed option is the only one left, so a refused grab falls through to
    the bite rather than costing the creature half its action.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    first = c.choose(["m249a2", "m249a1"], "m249a3: the first attack") or "m249a2"
    if not use(c.world, me, first, targets=[victim], spend=False):
        use(c.world, me, "m249a1", targets=[victim], spend=False)
    use(c.world, me, "m249a1", targets=[victim], spend=False)


@power(
    "m249a4",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
    requires=_has_hold,
    requires_text="the m249 must have a creature grabbed",
)
def m249a4(c: Cast) -> None:
    """The printed target is a creature this one already has hold of, which
    no `Target` can say -- so `requires` carries the half about the board and
    the body aims at whoever is actually in its grip.

    "The stun also ends if the m249 is no longer grabbing the target" is a
    second ending on top of the saving throw, so it is a watch on the
    relation being cleared rather than anything the duration can express.
    The watch is ended with the stun, or it would outlive the thing it is
    about.
    """
    me = c.me
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    hold = c.stunned(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def released(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.world.effects.end(hold, "the grab ended")

    watcher = c.watch(
        RelationCleared, released, until=When.ENCOUNTER, on=me, label=f"{c.ref} released"
    )
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the stun ended"))


# ==========================================================================
# m2890
# ==========================================================================


@power(
    "m2890a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 6),
)
def m2890a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2890a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 6),
)
def m2890a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2890a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2890a2(c: Cast) -> None:
    """One creature twice or two creatures once, which is what "two attacks"
    offers and what `UpTo(2)` lets the caller choose between. The row that
    prints the attack is used rather than copied, so its damage line stays in
    one place."""
    if c.target is None:
        return
    for _ in range(2 if len(c.targets) == 1 else 1):
        use(c.world, c.me, "m2890a1", targets=[c.target], spend=False)


_M2890_STIRRED = "an enemy enters or leaves a square adjacent to the m2890"


def _neighbour_stirs(world: World, me: int, ev: Any) -> bool:
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and ev.square in spread(squares(world, me), 1)
    )


@power(
    "m2890a3",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 3),
    trigger=_M2890_STIRRED,
    on=[
        Trigger(EnterSquare, when=_neighbour_stirs, text="an enemy enters"),
        Trigger(LeaveSquare, when=_neighbour_stirs, text="or leaves an adjacent square"),
    ],
)
def m2890a3(c: Cast) -> None:
    """Two printed triggers, so two are declared: `on=` takes a sequence and
    the row answers whichever happened.

    The square events rather than `AdjacencyGained` and `AdjacencyLost`:
    adjacency is diffed once the mover has arrived, so on the way out the
    enemy would already be gone, and these are announced while it is still
    standing in the square the sentence is about.
    """
    if c.target is not None and c.strike():
        c.hit()
        c.prone()


@power(
    "m2890a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 3, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m2890a4(c: Cast) -> None:
    """The card prints a blast and no target line at all, so the blast takes
    the enemies standing in it rather than everybody.

    The Effect line is a second, separate burst on the next turn, with no
    attack roll in it. It is armed once for the whole power -- `c.first` --
    and ends itself the moment it goes off: hung on `When.SONT` it would
    have been torn down first, because `Effects` subscribes to `TurnStart`
    when the world is built and so runs ahead of anything a row arms later.
    """
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)
    if not c.first:
        return
    me = c.me
    holder: list[Effect] = []

    def roar(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for foe in sorted(c.within(3, side="enemy")):
            c.flat(10, dtype=DamageType.THUNDER, on=foe)
        if holder:
            c.world.effects.end(holder[0], "it has roared")

    holder.append(
        c.watch(TurnStart, roar, until=When.ENCOUNTER, on=me, label="m2890a4 roar")
    )


_M2890_BLED = "the m2890 is first bloodied"


@power(
    "m2890a5",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2890_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2890_BLED),
)
def m2890a5(c: Cast) -> None:
    """The row put back is m2890a4.

    The line as filed names a ref that belongs to no stat block in the tree,
    which is a cross-reference the database lost. The only recharging attack
    this creature has is m2890a4, so that is what comes back and what it
    then uses. "First bloodied" needs no guard -- `Bloodied` is emitted on
    the crossing and nowhere else.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m2890a4")
    use(c.world, c.me, "m2890a4", trigger=c.trigger)


@power(
    "m2890a6",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=12),
)
def m2890a6(c: Cast) -> None:
    """An aftereffect is what follows when the first hold ends, whether that
    was a save or the clock, so it hangs off the hold's own ending rather
    than being applied alongside it -- applied alongside, the penalty would
    have started while the target was still stunned and run out early."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m3002
# ==========================================================================


@power(
    "m3002a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m3002a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()
        c.mark()


_M3002_SLIGHTED = (
    "an enemy marked by the m3002 makes a melee attack against an ally adjacent to it"
)


def _marked_swings_at_a_neighbour(world: World, me: int, ev: AttackDeclared) -> bool:
    """All four clauses, because each is a separate question: whose mark the
    attacker is under, what kind of swing it is, whose side the victim is on,
    and how close the victim is standing to the m3002."""
    who = ev.attacker
    if not world.relations.holds(Relation.MARKED_BY, me, who):
        return False
    if not by_melee(world, me, ev):
        return False
    victim = ev.target
    return (
        victim != me
        and team(world, victim) is team(world, me)
        and distance_between(world, me, victim) <= 1
    )


@power(
    "m3002a1",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5),
    trigger=_M3002_SLIGHTED,
    on=Trigger(AttackDeclared, when=_marked_swings_at_a_neighbour, text=_M3002_SLIGHTED),
)
def m3002a1(c: Cast) -> None:
    """An interrupt, so the blow lands before the one that opened it."""
    if c.target is not None and c.strike():
        c.hit()


@power(
    "m3002a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
    requires=_is_mounted,
    requires_text="the m3002 must be mounted",
)
def m3002a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3002a3",
    level=7,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M3002_SLIGHTED,
    on=Trigger(AttackDeclared, when=_marked_swings_at_a_neighbour, text=_M3002_SLIGHTED),
)
def m3002a3(c: Cast) -> None:
    """The blow is moved rather than stopped, which only an interrupt can do
    and only before the roll -- after it there is a result, and moving that
    would mean rolling again.

    The bonus is gated on the attacker rather than given a duration, because
    the printed line is about one attack; `_until_that_blow_lands` is what
    takes it away again. Declared with no target: the beneficiary is the
    m3002, and a row that took itself as a target would be aimed by the
    dispatcher at the enemy instead.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None or not c.redirect(to=c.me):
        return
    guard = c.bonus(
        Defense.AC,
        3,
        until=When.EOT,
        on=c.me,
        when=lambda ctx: ctx.get("attacker") == who,
    )
    _until_that_blow_lands(c, who, guard)


# ==========================================================================
# m3048
# ==========================================================================


@power(
    "m3048a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 3),
)
def m3048a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3048a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m3048a1(c: Cast) -> None:
    """A penalty to saving throws that is itself save-ends: the effect makes
    its own escape harder, which is what the printed line says and is the
    reason it is one effect rather than two."""
    if c.strike():
        c.hit()
        c.penalty("save", 5, until=When.SAVE_ENDS)


@power(
    "m3048a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=12),
)
def m3048a2(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the pull and the daze."""
    if c.strike():
        c.pull(5)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3048a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3048a3(c: Cast) -> None:
    """A disguise settled by an Insight check against a Bluff check, and
    nothing else -- declared inert rather than given an invented mechanic."""
    c.note("m3048a3: it passes for any Medium natural humanoid; Insight beats its Bluff")


# ==========================================================================
# m3102
# ==========================================================================


@power(
    "m3102a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 6),
)
def m3102a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3102a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 6),
)
def m3102a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3102a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d4", 0, kind=LIMITED),
    requires=_has_hold,
    requires_text="the m3102 must have a creature grabbed",
)
def m3102a2(c: Cast) -> None:
    """The printed recharge is a board state rather than a die: it comes back
    the moment nobody is carrying its effect any more. The number stays in
    the header, because that is what the card shows and what `actions.recharge`
    rolls; this is the printed sentence on top of it, and the two only ever
    agree to make the row available sooner.

    Any expiry is worth re-asking the question on -- the answer is about the
    board and not about which effect just ended -- and giving back a row that
    is already available costs nothing.
    """
    ref = c.ref
    _recharge_on(c, EffectExpired, lambda _ev: not c.suffering(ref))
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.condition(
        Condition.RESTRAINED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.UNTYPED),
    )


@power(
    "m3102a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3102a3(c: Cast) -> None:
    """Whoever it has hold of is read *before* the step: the pull is what
    keeps them in its grip, and asking afterwards would be asking about a
    grab the step may already have broken."""
    held = sorted(_holding(c))
    if not c.shift(1):
        return
    for who in held:
        if not c.adjacent(who):
            c.pull(1, on=who)


# ==========================================================================
# m324
# ==========================================================================


@power(
    "m324a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 6),
)
def m324a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m324a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m324a1(c: Cast) -> None:
    """The card prints a burst and no target line at all, so the burst takes
    the enemies standing in it rather than everybody."""
    if c.strike():
        c.hit()
        if c.size_of() in SMALL_ENOUGH:
            c.prone()


# ==========================================================================
# m364
# ==========================================================================


@power(
    "m364a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m364a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the penalty held per occupant."""
    _aura(
        c,
        1,
        lambda who: who in c.enemies() and _living(c, who),
        lambda who: c.penalty("attack", 2, until=When.ENCOUNTER, on=who),
    )


@power(
    "m364a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m364a1(c: Cast) -> None:
    """The pull comes before the grab, which is the order the card reads in
    and the only order in which the grab is made at arm's length."""
    if c.strike():
        c.hit()
        c.pull(2)
        c.grab()


@power(
    "m364a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 8),
)
def m364a2(c: Cast) -> None:
    """A creature already in its grip swaps the expression rather than adding
    to it, so the header keeps the printed line that rescales and the larger
    one is rolled here.

    The contagion is a disease track with a saving throw after the fight,
    which the engine has no model of, so it is noted rather than invented.
    """
    if not c.strike():
        return
    if c.target in _holding(c):
        c.damage("1d10", 12)
    else:
        c.hit()
    c.note("m364a2: the target is exposed to this stat block's disease")


# ==========================================================================
# m4854
# ==========================================================================


@power(
    "m4854a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4854a0(c: Cast) -> None:
    """An aura 1, with the halving held while its master stands inside.

    `c.insubstantial` is what halves everything a creature takes, and it is
    a property of the creature rather than of the damage -- which is how the
    printed line reads. Only one creature is ever eligible, so the aura holds
    at most one of these at a time.
    """
    _aura(
        c,
        1,
        lambda who: who == c.master(),
        lambda who: c.insubstantial(until=When.ENCOUNTER, on=who),
    )


@power(
    "m4854a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4854a1(c: Cast) -> None:
    """Shared sight, hearing and speech, and nothing else. Declared inert
    rather than given an invented mechanic."""
    c.note("m4854a1: its master sees, hears and speaks through it")


@power(
    "m4854a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m4854a2(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m4854a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 6),
)
def m4854a3(c: Cast) -> None:
    """Range 20/40: the header carries the short range, which is the only one
    the engine measures. An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


_M4854_TREASON = "an enemy marked by the m4854 attacks the m4854's master"


def _marked_swings_at_my_master(world: World, me: int, ev: AttackDeclared) -> bool:
    owners = world.relations.sources(Relation.MASTER_OF, me)
    return (
        bool(owners)
        and world.relations.holds(Relation.MARKED_BY, me, ev.attacker)
        and ev.target in owners
    )


@power(
    "m4854a4",
    level=7,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
    trigger=_M4854_TREASON,
    on=Trigger(AttackDeclared, when=_marked_swings_at_my_master, text=_M4854_TREASON),
)
def m4854a4(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.hit()


# ==========================================================================
# m494
# ==========================================================================


@power(
    "m494a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m494a0(c: Cast) -> None:
    """The whole effect ends, not just the condition: a save-ends hold
    carrying a daze and ongoing damage together is one printed effect, and
    ending half of it would leave a hold nothing could ever clear."""
    me = c.me

    def shake_off(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if any(cond in SHAKEN_OFF for cond in eff.conditions):
                c.world.effects.end(eff, "m494a0")

    c.watch(TurnEnd, shake_off, until=When.ENCOUNTER, on=me, label="m494a0")


@power(
    "m494a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m494a1(c: Cast) -> None:
    """A solo acting twice a round: a second slot in the initiative order.

    The printed line buys a free action at that count rather than a whole
    turn, and there is no way to hand out a turn with one action in it --
    `c.extra_turn` is what the engine has for a creature that acts again, so
    the rest of that turn's budget is spent once the attack is made.

    The spliced slot always sorts above its own, being ten higher, so the
    *first* of its turns each round is that one, which is how the two are
    told apart. Whichever attack it makes there is a real choice and is
    offered as one. If it is being held by a stun or a domination, that ends
    instead of the attack happening, as printed.
    """
    me = c.me
    slots: dict[int, int] = {}

    def strike(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        slots[c.world.round] = slots.get(c.world.round, 0) + 1
        if slots[c.world.round] != 1:
            return
        gripped = [
            eff
            for eff in c.world.effects.of(me)
            if any(cond in HELD_FAST for cond in eff.conditions)
        ]
        if gripped:
            for eff in gripped:
                c.world.effects.end(eff, "m494a1")
            return
        ref = c.choose(["m494a2", "m494a3"], "m494a1: which attack") or "m494a2"
        use(c.world, me, ref)
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = budget.move = budget.minor = 0

    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(init.rolled + 10)
    c.watch(TurnStart, strike, until=When.ENCOUNTER, on=me, label="m494a1")


@power(
    "m494a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 6),
)
def m494a2(c: Cast) -> None:
    """The burning lasts "until the grab ends", which is neither a clock nor
    a saving throw -- so it is held to the end of the fight and taken off
    when the relation is cleared. How much it burns for is read at the moment
    of the bite rather than each turn: the printed line fixes the number when
    the grab is made.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    c.grab(on=victim)
    burn = c.ongoing(
        10 if c.bloodied(me) else 5,
        DamageType.FIRE,
        on=victim,
        until=When.ENCOUNTER,
    )
    if burn is None:
        return

    def released(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.world.effects.end(burn, "the grab ended")

    watcher = c.watch(
        RelationCleared, released, until=When.ENCOUNTER, on=me, label=f"{c.ref} released"
    )
    burn.on_end.append(lambda: c.world.effects.end(watcher, "the burning stopped"))


@power(
    "m494a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m494a3(c: Cast) -> None:
    """One creature twice or two creatures once, which is what the printed
    line offers and what `UpTo(2)` lets the caller choose between.

    The count of what it already has hold of is taken inside the loop: two
    swings at one creature can each add to it, and asking once would have let
    the second blow grab a third victim.
    """
    for _ in range(2 if len(c.targets) == 1 else 1):
        if not c.strike():
            continue
        c.hit()
        if len(_holding(c)) < 2:
            c.grab()


@power(
    "m494a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d12", 7, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m494a4(c: Cast) -> None:
    """"Creatures in the blast" is everything caught, not only enemies.

    Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here --
    on the miss as well, since half of the larger number is what the printed
    miss line halves.
    """
    hurt = c.bloodied(c.me)
    if c.strike():
        if hurt:
            c.damage("2d12", 17, dtype=DamageType.FIRE)
        else:
            c.hit()
    elif hurt:
        c.half_damage("2d12", 17, dtype=DamageType.FIRE)
    else:
        c.hit(half=True)


_M494_SLIPPED = "an enemy leaves a square within 2 squares of the m494"


def _near_square_vacated(world: World, me: int, ev: LeaveSquare) -> bool:
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and ev.square in spread(squares(world, me), 2)
    )


@power(
    "m494a5",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 5),
    trigger=_M494_SLIPPED,
    on=Trigger(LeaveSquare, when=_near_square_vacated, text=_M494_SLIPPED),
)
def m494a5(c: Cast) -> None:
    """`LeaveSquare` rather than `MoveEnd`: the square is announced while its
    owner is still standing in it, which is where the printed reach of 3 is
    measured from."""
    if c.target is not None and c.strike():
        c.hit()
        c.prone()


_M494_BLED = "the m494 is first bloodied"


@power(
    "m494a6",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M494_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M494_BLED),
)
def m494a6(c: Cast) -> None:
    """The row put back is m494a4, for the reason m2890a5 gives: the ref as
    filed belongs to no stat block in the tree, and the only recharging
    attack this creature has is that one."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m494a4")
    use(c.world, c.me, "m494a4", trigger=c.trigger)


# ==========================================================================
# m6369
# ==========================================================================


@power(
    "m6369a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5),
)
def m6369a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6369a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m6369a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6369a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6369a2(c: Cast) -> None:
    """Threatening reach: a window opened at two squares as well as one.

    `movement.step` opens one only for an enemy leaving the ring one square
    out, so the second ring has to be opened here. `LeaveSquare` is the
    moment to do it -- the mover is still standing in the square -- but it
    says nothing about what kind of move is under way, so the kind is taken
    off the `MoveStart` that opened it and a shift or a teleport is let past,
    exactly as the engine's own rule lets them past.

    The window is opened for every square of the outer ring that is vacated
    rather than only for a move that ends outside reach, which the engine
    can do because it knows the destination and this does not. That over-offers
    and cannot over-attack: an opportunity action is once per other creature's
    turn, and `Encounter.can_spend` refuses the rest.
    """
    me = c.me
    kinds: dict[int, str] = {}

    def started(ev: MoveStart) -> None:
        kinds[ev.actor] = ev.kind_

    def stepped(ev: LeaveSquare) -> None:
        who = ev.actor
        if who == me or kinds.get(who, "walk") in SAFE_MOVES:
            return
        if who not in c.enemies():
            return
        near = spread(squares(c.world, me), 2)
        if ev.square in near and ev.square not in spread(squares(c.world, me), 1):
            c.provoke(me, on=who, why="m6369a2")

    c.watch(MoveStart, started, until=When.ENCOUNTER, on=me, label="m6369a2 kind")
    c.watch(LeaveSquare, stepped, until=When.ENCOUNTER, on=me, label="m6369a2")


# ==========================================================================
# m717
# ==========================================================================


@power(
    "m717a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m717a0(c: Cast) -> None:
    """An aura 1 for the board to draw, biting at the start of a turn.

    Not `_aura`, whose hold is carried for as long as its owner is inside:
    this one is a fresh slowing each turn, measured by distance, and it lasts
    to the start of the victim's *own* next turn whether or not it is still
    standing in the aura by then.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def seethe(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, seethe, until=When.ENCOUNTER, on=me, label="m717a0")


@power(
    "m717a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m717a1(c: Cast) -> None:
    """Only the shove half of the swarm trait.

    `c.immovable` refuses every kind of forced movement and the printed line
    refuses two of them, so the refusal is written against `ForcedMove`
    itself, which carries the row doing the shoving and can therefore tell a
    sword from a burst.

    Not written: sharing a square with another creature, an enemy entering
    that square and finding it difficult, and squeezing through gaps. All
    three are facts about occupancy that the grid decides, and no `Cast`
    method reaches them. See the report.
    """
    me = c.me

    def refuse(ev: ForcedMove) -> None:
        if ev.target != me:
            return
        p = get(getattr(ev, "power", "") or "")
        if p is not None and p.reach.kind in ("melee", "ranged"):
            ev.cancel("a swarm is not shoved by a sword or an arrow")

    c.watch(
        ForcedMove,
        refuse,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m717a1",
    )


@power(
    "m717a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m717a2(c: Cast) -> None:
    c.ignores_difficult("web", until=When.ENCOUNTER)


@power(
    "m717a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 3),
)
def m717a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
