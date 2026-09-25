"""Monster abilities, level 12: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("2d8", 11)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the eleven levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; and a helper written for an
earlier level is imported rather than copied.

Four things this file had to settle.

**Concealment is a number, not a state.** The engine keeps none: what
concealment *is* is -2 to attack rolls against the concealed creature, which
is how level 3 wrote it and how m4797a3 writes it here. Total concealment is
the one half the engine does hold, because being unseen is the `HIDDEN_FROM`
relation -- so the printed "if it is in an obscured square" is asked of the
zones, which is the only place the board records a square you cannot see
into.

**Damage shared with a swallowed creature is the packet, halved.** m4797a2's
"the attack deals half damage to the m4797 and half damage to the target" is
`DamageRolled` in the interrupt window, where `amount` is still negotiable
and read back. The second half is dealt to the victim from there, and only
while the grab is live -- which is asked of the relation each time rather
than remembered, because a grab can end between one blow and the next.

**A row printed as three attacks with one header.** m4806a4 fires one or two
rays of three, each at a different enemy, and each has its own defence and
its own damage. `Attack` and `attack_alt` are two branches and this is
three, so the header declares none and the bonuses go through
`scaling.trim` by hand -- the same arrangement a printed secondary attack
has used since level 2.

**"Until it attacks or until the end of its next turn" is two endings and
one hold.** `_vanish` is exactly that pair: the veil runs on a clock and
`AttackRolled` ends it early, whichever way the die falls.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.skirmishers import _grabbing
from combat_engine.content.monsters.level_04.skirmishers import (
    _grabbed_or_grabbing,
    _not_the_prisoner,
    _until_the_grab_ends,
)
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import _aura, _holding
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
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
    Cast,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Relation,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    by_melee,
    by_ranged,
    power,
)
from combat_engine.engine.events import DamageRolled, RelationCleared, RelationSet
from combat_engine.engine.query import alive, distance_between, is_
from combat_engine.engine.triggers import Trigger, both, either

#: The three rays m4806a4 chooses between. Written out because the header
#: holds one attack line and this row prints three, each with its own
#: defence and its own damage.
_M4806_RAYS = ("blinding", "thundering", "shadowbond")


def _in_the_dark(c: Cast, who: int) -> bool:
    """Is that creature standing somewhere sight does not reach?

    "An obscured square" has no component of its own; a zone that blocks
    sight is the only thing on the board that makes one, and `blocks_sight`
    is the flag `query.cover_between` already reads.
    """
    for zid, zone in c.world.zones.all():
        if zone.blocks_sight and who in c.world.zones.occupants(zid):
            return True
    return False


def _concealed(c: Cast, who: int, until: When) -> None:
    """Concealment, which is -2 to attack rolls against that creature.

    The engine keeps no state for it and does not need to: the whole of what
    concealment does is subtract two from whoever swings, and a gated
    modifier on each enemy asked about its *target* says exactly that. The
    same trick from the other end that level 3 used for a fog zone.
    """
    for foe in sorted(c.enemies()):
        c.penalty(
            "attack", 2, until=until, on=foe, kind="untyped",
            when=lambda ctx: ctx.get("target") == who,
        )


# ==========================================================================
# m202
# ==========================================================================


def _under_two_holds(world: World, eid: int) -> bool:
    """The printed Requirement: it has fewer than two creatures in its grip.

    Counted off the relation rather than remembered, because a grab can end
    between one use of the row and the next.
    """
    return len(_holding(world, eid)) < 2


@power(
    "m202a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m202a0(c: Cast) -> None:
    """Unseen unless it has hold of something or something has hold of it.

    Total concealment is a standing property rather than a thing it does, so
    the relation is set directly rather than through `c.hide`: a hold with a
    duration would be re-applied every time an attack broke it, and this
    line is never broken by attacking. It is re-established whenever
    anything gives it away and whenever any grab ends, and dropped the
    moment a grab begins at either end of it. The arrangement the same
    sentence settled on eight levels down.
    """
    me = c.me

    def veil() -> None:
        if _grabbed_or_grabbing(c):
            return
        for foe in c.enemies():
            if not c.is_hidden(from_=foe):
                c.world.relations.set(Relation.HIDDEN_FROM, me, foe)

    def again(_ev: Any) -> None:
        veil()

    def caught(ev: RelationSet) -> None:
        if ev.kind_ is Relation.GRABBED_BY and me in (ev.source, ev.target):
            c.unhide()

    veil()
    c.watch(TurnStart, again, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(RelationCleared, again, until=When.ENCOUNTER, on=me, label=f"{c.ref} again")
    c.watch(RelationSet, caught, until=When.ENCOUNTER, on=me, label=f"{c.ref} held")


@power(
    "m202a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 2),
    requires=_under_two_holds,
    requires_text="the m202 must not have two creatures grabbed",
)
def m202a1(c: Cast) -> None:
    """The burn is hung on the grab rather than on a saving throw, which is
    what the printed duration says: "until the grab ends" is a clock the
    enum has no word for, and `When.SAVE_ENDS` would let a creature shake
    the damage off while still held.

    The printed escape DC has nowhere to go: a grab is a relation and the
    engine has no contest to put a number in.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    _until_the_grab_ends(c, victim, c.ongoing(10, until=When.ENCOUNTER, on=victim))


@power(
    "m202a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
)
def m202a2(c: Cast) -> None:
    """No damage line at all: the hold is the whole of the hit."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


_M202_STRUCK = "the m202 is attacked by an enemy other than the one it holds"


@power(
    "m202a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    requires=_grabbing,
    requires_text="the m202 must have a creature grabbed",
    trigger=_M202_STRUCK,
    on=Trigger(
        AttackDeclared,
        when=both(_not_the_prisoner, either(by_melee, by_ranged)),
        text=_M202_STRUCK,
    ),
)
def m202a3(c: Cast) -> None:
    """It holds the prisoner in the way.

    The printed trigger reads "is hit by", and `c.redirect` only works
    before the die is down -- after it there is a result that would have to
    be thrown out and rolled again against a different defence. So the
    declaration is what is answered, which is the window the printed effect
    actually needs, and `_not_the_prisoner` is that sentence written out.

    The card spells the recharge as another stat block's id; the row every
    sentence plainly means is this creature's own grab. It is put on top of
    the die the database files, and the two only ever agree to give the row
    back sooner.
    """
    me = c.me
    _recharge_on(c, Hit, lambda ev: ev.attacker == me and ev.power == "m202a1")
    held = _holding(c.world, me)
    if held:
        c.redirect(to=held[0])


# ==========================================================================
# m4797
# ==========================================================================


def _not_holding(world: World, eid: int) -> bool:
    return not _holding(world, eid)


@power(
    "m4797a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m4797a0(c: Cast) -> None:
    """An aura whose occupants carry the penalty for as long as they are
    inside, diffed by the zone rather than recomputed.

    Deafness is asked when a creature enters rather than continuously: a
    creature deafened while standing in it keeps the penalty until it steps
    out and back, which is the same approximation every aura in the tree
    with a condition in its membership test makes.
    """
    def nondeafened(who: int) -> bool:
        return who in c.enemies() and not is_(c.world, who, Condition.DEAFENED)

    def cowed(who: int) -> Effect | None:
        return c.penalty("attack", 2, until=When.ENCOUNTER, on=who, kind="untyped")

    _aura(c, 2, nondeafened, cowed)


@power(
    "m4797a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m4797a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4797a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    requires=_not_holding,
    requires_text="the m4797 must not have a creature grabbed",
)
def m4797a2(c: Cast) -> None:
    """It folds somebody inside itself.

    No damage line: the grab, what comes with it and the shared wounds are
    the whole of the hit. The four conditions and the burn are one hold, so
    the victim never gets four saving throws against one printed sentence,
    and they all run until the grab ends rather than on a clock of their
    own.

    "A square within the m4797's space" is a square the grid will not give:
    the m4797 is standing in all of them and `movement.forced` stops dead at
    the first square it cannot enter. A pull of one is as close as the board
    allows and is noted.

    The shared damage is `DamageRolled` in the interrupt window, where the
    amount is still negotiable and is read back. Whether the grab is still
    live is asked of the relation each time rather than remembered.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.pull(1, on=victim)
    c.note("m4797a2: the target is drawn into the m4797's own space")
    grip = c.grab(on=victim)
    hold = c.condition(
        Condition.BLINDED,
        Condition.DAZED,
        Condition.RESTRAINED,
        until=When.ENCOUNTER,
        on=victim,
        ongoing=(10, DamageType.UNTYPED),
    )
    _until_the_grab_ends(c, victim, hold)

    def shared(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if not c.world.relations.holds(Relation.GRABBED_BY, me, victim):
            return
        half = ev.amount // 2
        ev.amount -= half
        if half:
            c.flat(half, dtype=ev.dtype, on=victim)

    watcher = c.watch(
        DamageRolled, shared, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )
    if grip is not None:
        grip.on_end.append(
            lambda: c.world.effects.end(watcher, "it has let go")
        )


@power(
    "m4797a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m4797a3(c: Cast) -> None:
    """Concealment, and total concealment where sight cannot reach.

    Concealment is the -2 and nothing else -- the engine keeps no state for
    it -- while total concealment is being unseen, which it does keep. Which
    one this is depends on where the creature is standing, and a zone that
    blocks sight is the only thing that makes a square obscured.
    """
    if _in_the_dark(c, c.me):
        c.invisible(until=When.SONT)
    else:
        _concealed(c, c.me, When.SONT)


# ==========================================================================
# m4806
# ==========================================================================


@power(
    "m4806a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4806a0(c: Cast) -> None:
    """Standing on both sides of it buys nothing."""
    c.cannot_be_flanked()


@power(
    "m4806a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4806a1(c: Cast) -> None:
    """Read off the `Hit` rather than asked of the board again: a one-shot
    grant of combat advantage has already been spent by the time the blow is
    announced, so asking a second time comes back false on exactly the
    attacks this rider is for.

    Dealt as its own packet rather than as a damage modifier, which would
    add to whatever else was riding along.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.damage("2d6", on=ev.target, detail=c.ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4806a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4806a2(c: Cast) -> None:
    """Twenty back at the end of a turn it spent entirely out of sight.

    "Has remained invisible since the start of its turn" is two readings and
    the state in between cannot be reconstructed afterwards, so the start of
    the turn is noted and the end of it compared against the note. Being
    unseen is the `HIDDEN_FROM` relation, which is what `c.is_hidden` asks;
    attacking clears it, so a turn it swung in answers no by itself.
    """
    me = c.me
    kept = {"unseen": False}

    def opened(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            kept["unseen"] = c.is_hidden()

    def closed(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not kept["unseen"] or not c.is_hidden():
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.heal(20, on=me)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")
    c.watch(TurnEnd, closed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4806a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 11),
)
def m4806a3(c: Cast) -> None:
    if c.strike():
        c.hit()


def _shadowbond(c: Cast, victim: int) -> None:
    """The hold the third ray leaves, and the cover it gives its own side.

    The concealment is a gated penalty on each enemy, asked about the
    creature being swung at and how far that creature is from the victim --
    both of which are read at the moment of the roll, which is the only
    moment either is knowable. It runs until the hold ends rather than on a
    clock, because "until the effect ends" is the printed duration and a
    saving throw is what ends it.
    """
    me = c.me
    hold = c.immobilized(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    shadowy = {me, *(mate for mate in c.allies() if c.is_kind("shadow", on=mate))}

    def shrouded(ctx: dict[str, Any]) -> bool:
        aimed = ctx.get("target")
        return (
            aimed in shadowy
            and alive(c.world, victim)
            and distance_between(c.world, aimed, victim) <= 5
        )

    veils = [
        c.penalty(
            "attack", 2, until=When.ENCOUNTER, on=foe, kind="untyped", when=shrouded
        )
        for foe in sorted(c.enemies())
    ]

    def lift() -> None:
        for veil in veils:
            if veil is not None and not veil.ended:
                c.world.effects.end(veil, "the bond is broken")

    hold.on_end.append(lift)


@power(
    "m4806a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    no_provoke=True,
)
def m4806a4(c: Cast) -> None:
    """One or two rays, each at a different enemy.

    The header declares no attack line: there are three of them, with three
    defences and three damage lines, and `attack` and `attack_alt` are two
    branches. So each ray's printed bonus goes through `scaling.trim` by
    hand the way a printed secondary attack has since level 2, and its
    damage is dealt as its own packet.

    Declared with no target, because how many rays it fires and which
    creature each goes to is the choice the printed line is made of, and a
    target list chosen before the body runs settles it.
    """
    me = c.me
    bonus = c.world.scaling.trim(15, c.level)
    spent: set[int] = set()
    for shot in range(2):
        prey = sorted(
            foe
            for foe in c.enemies()
            if foe not in spent and alive(c.world, foe) and c.distance(foe) <= 10
        )
        if not prey:
            return
        if shot and not c.may("fire a second ray", who=me, default=True):
            return
        victim = c.choose(prey, f"m4806a4: who the {shot + 1} ray goes to")
        ray = c.choose(list(_M4806_RAYS), "m4806a4: which ray")
        if victim is None or ray is None:
            return
        spent.add(victim)
        if ray == "blinding":
            if c.attack(bonus, REF, on=victim):
                c.damage("1d8", 6, dtype=DamageType.RADIANT, on=victim)
                c.blinded(until=When.EOTNT, on=victim)
        elif ray == "thundering":
            if c.attack(bonus, FORT, on=victim):
                c.damage("3d6", 10, dtype=DamageType.THUNDER, on=victim)
                c.condition(Condition.DEAFENED, until=When.EOTNT, on=victim)
        elif c.attack(bonus, WILL, on=victim):
            c.damage("3d6", 5, dtype=DamageType.NECROTIC, on=victim)
            _shadowbond(c, victim)


@power(
    "m4806a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
)
def m4806a5(c: Cast) -> None:
    """"Until it attacks or until the end of its next turn" is two endings
    on one hold, which is exactly what `_vanish` holds: the clock runs, and
    `AttackRolled` ends it early whichever way the die falls."""
    c.teleport(20)
    _vanish(c, When.EONT)


@power(
    "m4806a6",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m4806a6(c: Cast) -> None:
    """No damage line: the opening is the whole of the hit, and it is
    offered to its whole side -- which is what a printed "grants combat
    advantage" with nobody named means."""
    if c.strike():
        c.grants_advantage(until=When.EONT, to="allies")
