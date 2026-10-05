"""Monster abilities, level 1, lurkers: the second sweep.

Five stat blocks whose rows were still undeclared. The level's first sweep is
in `skirmishers.py`, `brutes.py`, `artillery.py` and `controllers.py`; the
split is by *when* the work was done rather than by what the creatures are,
and the conventions are the ones those files settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=6)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* being unseen is one state. `c.invisible` and `c.hide` set the same
  `HIDDEN_FROM` relation and differ only in how it runs out, and
  `resolve.attack` clears it for whoever swung -- which is the printed
  "until it attacks" for free.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import _any_enemy_suffering
from combat_engine.content.monsters.level_02.skirmishers import _advantage_rider
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Target,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.events import AttackDeclared, DamageRolled, ZoneEntered
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import cover_between, distance_between, enemies
from combat_engine.engine.triggers import Trigger, targets_me


def _shrug_off(c: Cast) -> None:
    """Roll a d20 and take nothing at all on a 10 or better.

    Declared on `DamageRolled`, which is one of the five events a listener may
    refuse, and from an interrupt, which is the only window that may refuse
    one. The die is rolled whatever it shows, because the card spends the use
    on the attempt rather than on the success.
    """
    if c.roll("1d20") >= 10:
        c.cancel()


def _can_vanish(world: World, eid: int) -> bool:
    """Cover, concealment, or nobody close enough to be watching.

    `cover_between` is the one number cover and concealment both come out of,
    measured from each enemy in turn -- cover is a fact about two positions
    and there is no single answer to "does it have cover".
    """
    foes = enemies(world, eid)
    if not any(distance_between(world, eid, f) <= 5 for f in foes):
        return True
    return any(cover_between(world, f, eid) is not Cover.NONE for f in foes)


# --------------------------------------------------------------------------
# m3436
# --------------------------------------------------------------------------


@power(
    "m3436a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage(bonus=5, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m3436a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3436a1",
    level=1,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it would take damage",
    on=Trigger(DamageRolled, targets_me, "it would take damage"),
)
def m3436a1(c: Cast) -> None:
    """"The first time in an encounter" is the usage line, not a counter: an
    encounter row has exactly one use and the dispatcher spends it."""
    _shrug_off(c)


@power(
    "m3436a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="helpless or unconscious creature"),
    keywords=[Keyword.PSYCHIC],
    requires=_any_enemy_suffering(Condition.HELPLESS, Condition.UNCONSCIOUS),
    requires_text="must have a helpless or unconscious creature to feed on",
    dropped=("Target.condition",),
)
def m3436a2(c: Cast) -> None:
    """No attack line at all -- the damage is automatic against something that
    cannot stop it -- so the restriction is the whole of the row's gate and is
    asked in the body: `Target` filters on side and size and not on what a
    creature is suffering."""
    if not (c.is_(Condition.HELPLESS) or c.is_(Condition.UNCONSCIOUS)):
        return
    c.flat(5, dtype=DamageType.PSYCHIC)
    c.temp_hp(10, on=c.me)


# --------------------------------------------------------------------------
# m4302
# --------------------------------------------------------------------------


@power(
    "m4302a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8"),
)
def m4302a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4302a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4302a1(c: Cast) -> None:
    """Melee and ranged only, which is what the card names -- a close burst
    from this creature gets nothing. Read off the roll rather than asked of
    the board afterwards, because `resolve.attack` clears `HIDDEN_FROM` the
    moment the attack is over."""
    _advantage_rider(c, "1d6", ("melee", "ranged"))


@power(
    "m4302a2",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4302a2(c: Cast) -> None:
    """Two creatures changing places is `c.swap`, not a shift into an occupied
    square followed by a slide out of it: the intermediate state the card
    describes is illegal, and the only reason it prints the ally's move as a
    free action is to say the ally is not being forced. An ordinary shift when
    there is nobody to trade with."""
    friend = next((a for a in c.allies() if c.adjacent(a)), None)
    if friend is None or not c.swap(friend):
        c.shift(1)


@power(
    "m4302a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4302a3(c: Cast) -> None:
    """Refused at the declaration, in the `BEFORE` window, so nothing is
    rolled and no rider fires -- the same shape `c.cannot_attack` uses, which
    is the nearest verb and bars a creature outright rather than conditionally.

    Close and area attacks are untouched: the card names melee and ranged, and
    a burst does not pick out one enemy to aim at.
    """
    me, ref = c.me, c.ref

    def refuse(ev: AttackDeclared) -> None:
        if ev.target != me:
            return
        p = get(ev.power)
        if p is None:
            return
        if p.reach_of(getattr(ev, "branch", 0)).kind not in ("melee", "ranged"):
            return
        shooter = ev.attacker
        span = distance_between(c.world, shooter, me)
        if any(
            distance_between(c.world, shooter, other) < span
            for other in enemies(c.world, shooter)
            if other != me
        ):
            ev.cancel(f"{ref}: not the nearest enemy")

    c.watch(
        AttackDeclared, refuse, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{ref} overlooked",
    )


# --------------------------------------------------------------------------
# m4456
# --------------------------------------------------------------------------


@power(
    "m4456a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage(bonus=4, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m4456a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4456a1",
    level=1,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits it",
    on=Trigger(DamageRolled, targets_me, "an attack hits it"),
)
def m4456a1(c: Cast) -> None:
    """Declared on the damage rather than on the `Hit` the card names as the
    trigger: what the row does is take none, and `DamageRolled` is the
    refusable event that decides that. Cancelling the hit instead would also
    strip whatever else the attack was carrying."""
    _shrug_off(c)


# --------------------------------------------------------------------------
# m5752
# --------------------------------------------------------------------------


@power(
    "m5752a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 4),
)
def m5752a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5752a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature granting combat advantage"),
    attack=Attack(vs=AC, printed=6),
    damage=Damage("4d4"),
    dropped=("Target.grants_ca",),
)
def m5752a1(c: Cast) -> None:
    """The ongoing damage runs "until the grab ends", which is not one of the
    durations -- so it is laid for the encounter and ended off the grab's own
    `on_end`, which is the only moment that can be seen.

    `label=` records the target restriction for the card and
    `Target.relation` is the gap: the header filters on side and size, so the
    row is offered against a creature that is not granting it combat
    advantage.
    """
    if not c.strike():
        return
    c.hit()
    if c.grabbing():
        return
    held = c.grab()
    burn = c.ongoing(5, until=When.ENCOUNTER)
    if held is not None and burn is not None:
        held.on_end.append(lambda: c.world.effects.end(burn, c.ref))


@power(
    "m5752a2",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m5752a2(c: Cast) -> None:
    """`at="fly"` rather than a bare `c.move`: the pathfinder measures
    `query.speed`, which is the ground speed, and this creature's is slower
    than its wings."""
    c.move(3, at="fly")


@power(
    "m5752a3",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_can_vanish,
    requires_text="must have cover, concealment, or no enemies within 5 squares",
)
def m5752a3(c: Cast) -> None:
    """"Until it attacks" needs nothing said: `resolve.attack` clears
    `HIDDEN_FROM` for whoever swung, so the clock is the only half left to
    declare."""
    c.invisible(until=When.EONT)


# --------------------------------------------------------------------------
# m6670
# --------------------------------------------------------------------------


@power(
    "m6670a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 3),
)
def m6670a0(c: Cast) -> None:
    """"Was invisible to the target **when it attacked**" has to be asked
    before the swing: the attack gives the creature away, so by the time there
    is a hit to read the answer is always no."""
    unseen = c.is_hidden(from_=c.target)
    if not c.strike():
        return
    if unseen:
        c.damage("4d4", 6)
    else:
        c.hit()


@power(
    "m6670a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6670a1(c: Cast) -> None:
    """Unseen first, then the move, in that order: a creature that vanishes
    before it goes is not watched on the way. The "until it hits or misses"
    half is `resolve.attack`'s own doing."""
    c.invisible(until=When.EONT)
    c.shift(3)


@power(
    "m6670a2",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.blindsight()",),
)
def m6670a2(c: Cast) -> None:
    """The cloud is a zone that blocks sight and blinds whatever stands in it,
    arrived there or caught by it. The creature's own exemption is the dropped
    clause: `blocks_sight` is a property of the squares and there is no sense
    that reads through one, which is what `c.blindsight` would be.

    A Close burst 1 is three squares across, so a Medium creature inside it is
    "entirely in the cloud" by standing there at all.
    """
    me = c.me
    fog = c.area()
    cloud = c.zone(fog, blocks_sight=True, until=When.EONT, label=f"{c.ref} cloud")
    for caught in c.in_squares(fog):
        if caught != me:
            c.blinded(until=When.EONT, on=caught)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == cloud and ev.actor != me:
            c.blinded(until=When.EONT, on=ev.actor)

    c.watch(ZoneEntered, walked_in, until=When.EONT, on=me, label=f"{c.ref} cloud")
