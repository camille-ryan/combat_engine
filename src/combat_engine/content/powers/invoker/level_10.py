"""Invoker, level 10: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AREA_OR_CLOSE,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    DamageApplied,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    PowerUsed,
    Ranged,
    Summon,
    SurgeSpent,
    Trigger,
    When,
    both,
    enemy_within,
    get,
    hits_me,
    power,
)
from combat_engine.engine.types import Light


def _my_area_power(world: Any, me: int, ev: Any) -> bool:
    """"You use an area or a close attack power." `by_melee` lumps close
    attacks in with melee ones and `by_ranged` lumps areas in with ranged
    ones, so neither says this."""
    if getattr(ev, "actor", None) != me:
        return False
    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach.kind in AREA_OR_CLOSE


@power(
    "p11298",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p11298(c: Cast) -> None:
    """**Both halves play.** This row was once marked, on the true-at-the-
    time reading that `c.aura` took `radius`, `label`, `until`, `on`,
    `sustain` and `difficult` and no obscurity of any kind -- so *"squares
    inside the zone are heavily obscured"* had nowhere to go on an aura.
    `Zones.aura` passes `obscured` through now; the history is below
    because the near miss is still worth knowing.

    Checked against the near miss rather than assumed: `c.zone` **does**
    take `obscured=` with `obscured_for=`, and eight other rows of this
    walk were finished with it. An aura is the one shape it does not
    reach, and `c.move_zone` refuses an aura for the same reason -- the
    printed rule is that an aura moves with its owner.

    **Both halves play now, and the gap was the same shape as
    `difficult` one field over.** `Zone.obscured` has always existed and
    `Zones.create` has always taken it; `Zones.aura` did not pass it on,
    so *"squares inside the zone are heavily obscured"* was sayable of a
    static zone and not of one centred on its caster. Nine rows were once
    marked blocked for `difficult` for exactly this reason, and
    `Zones.aura`'s own docstring records that history.

    `Light.DARK` is "heavily obscured", which is `c.zone`'s own mapping --
    `Light.DIM` would be "lightly". #1341."""
    swarm = c.aura(3, until=When.SUSTAIN, sustain=MINOR,
                   obscured=Light.DARK)

    def bite(ev: Bloodied, z: int = swarm) -> None:
        if ev.actor in c.world.zones.occupants(z):
            c.dazed(on=ev.actor, until=When.EOTNT)

    c.watch(Bloodied, bite, until=When.ENCOUNTER)


@power(
    "p2886",
    level=10,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FEAR],
    trigger="an enemy within 5 squares of you makes an attack roll against you",
    on=Trigger(
        AttackDeclared,
        both(hits_me, enemy_within(5)),
        "an enemy within 5 squares attacks you",
    ),
)
def p2886(c: Cast) -> None:
    """The shove waits for the attack to finish, which is both outcomes of
    it, so the latch is shared between the two watches."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.EOT, once=True)
    shoved: list[int] = []

    def recoil(after: Hit | Miss, by: int = foe) -> None:
        if shoved or getattr(after, "attacker", None) != by:
            return
        shoved.append(1)
        c.push(3, on=by)

    c.watch(Hit, recoil, until=When.EOT)
    c.watch(Miss, recoil, until=When.EOT)


@power(
    "p3351",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p3351(c: Cast) -> None:
    """Nothing announces an ally being *offered* a surge, only one being
    spent, so this answers the spend: the ally's surge goes back into its
    pool and the caster's comes out instead, which leaves the board where
    the printed line leaves it."""

    def cover(ev: SurgeSpent) -> None:
        who = ev.actor
        if who == c.me or who not in c.within(10, side="ally"):
            return
        if not c.may("spend a surge on that ally's behalf", who=c.me, default=False):
            return
        if not c.spend_surge(on=c.me):
            return
        theirs = c.world.get(who, Health)
        if theirs is not None:
            theirs.surges += 1

    c.watch(SurgeSpent, cover, until=When.ENCOUNTER)


@power(
    "p7193",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p7193(c: Cast) -> None:
    """Written to the erratum: the bonus lasts to the *end* of the ally's
    next turn. It is gated on the attacker, so it only helps against the
    creature that dealt the damage."""
    ground = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    mine = {c.me, *c.allies()}

    def avenge(ev: DamageApplied, z: int = ground) -> None:
        mate = ev.target
        if mate not in mine or mate not in c.world.zones.occupants(z):
            return
        c.bonus(
            "attack",
            2,
            on=mate,
            kind="power",
            until=When.EOTNT,
            when=lambda ctx, foe=ev.source: ctx.get("target") == foe,
        )

    c.watch(DamageApplied, avenge, until=When.ENCOUNTER)


@power(
    "p7194",
    level=10,
    cls="invoker",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    trigger="you use an area or a close attack power and an ally is in the area",
    on=Trigger(PowerUsed, _my_area_power, "you use an area or a close attack power"),
)
def p7194(c: Cast) -> None:
    """`PowerUsed` carries the targets but not the origin, so the second
    half of the printed trigger -- the ally standing *in* the area -- has
    nothing to measure against and is not declared; the burst 10 target
    line carries the rest of it."""
    c.shift(c.int_mod, who=c.target)


@power(
    "p11296",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.SUMMONING],
    summon=Summon(
        speed=6, modes=("fly",),
        commands=((STANDARD, "p11296c1"), (MOVE, "p11296c0")),
    ),
)
def p11296(c: Cast) -> None:
    """**Its standard command heals rather than attacks, which is the case
    a shared `attack` field could not express at all** -- `c.command` rolls
    that line and there was nothing for it to read. `dsl.Summon.commands`
    names a row, and a row is free not to be an attack. #1360.

    **The marker is re-pointed rather than dropped, because the second
    command has a genuine residue.** The move action is *"the angel and one
    ally adjacent to it fly 8 squares. The ally must land at the end of
    this movement, or he or she falls."* Granting and aiming it is the same
    as any other command; what is missing is the fall -- nothing drops a
    creature that ends a **forced flight** in the air, where
    `falling.AIRBORNE` only keeps a flyer up because *"a flyer is not
    settled; it is where it means to be"*. An ally carried by somebody
    else's flight is exactly the case that reading excludes, so
    `falling.drop(forced_flight=)` is the one gap and this row is the
    first to want it.

    `Summon.modes` carries no speed, so the printed "fly 8" is set from the
    body."""
    angel = c.summon_inline(get(c.ref).summon, at=c.origin)
    if angel:
        c.mode("fly", 8, on=angel, until=When.ENCOUNTER)


@power(
    "p11296c1",
    level=10,
    # **`cls=""`, and this is load-bearing rather than tidiness.** A
    # command row declared with its class joins that class's power pool:
    # the nine declared here are `AT_WILL` at a character level, so with a
    # class on them they shifted the invoker draw and `f1491` -- which
    # triggers on an invoker class feature -- went from firing to UNUSED on
    # the wide sweep at `d2899ec7`. They are never dealt (measured: no
    # command ref reaches a dealt hand), so the cost was the *draw moving*,
    # not a bad card being offered. A summon's command is not a power a
    # character can take, so it belongs to no class.
    cls="",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p11296c1(c: Cast) -> None:
    """*"Standard Action: Melee 1; targets one ally; the ally regains 1d6
    hit points."*

    **A command that is not an attack**, which is the shape no field on
    `Summon` could carry: `attack` and `damage` are the only two it has and
    `c.command` rolls them. A row has no such constraint -- this one
    declares no `attack=` at all and heals.

    `ONE_ALLY` is the printed target line, and it is the angel's allies
    that are meant: the row is used *by* the angel, which stands on its
    summoner's side, so the pool is the party.
    """
    # `c.heal` takes a number, not an expression -- the idiom the
    # runepriest and ardent at-wills use.
    c.heal("1d6")


@power(
    "p11296c0",
    level=10,
    # `cls=""` for the reason `p11296c1` above gives at length: a command
    # row declared with its class joins that class's draw.
    cls="",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p11296c0(c: Cast) -> None:
    """*"Move Action: The angel and one ally adjacent to it fly 8 squares.
    The ally must land at the end of this movement, or he or she falls."*

    **The command was not declared at all**, which is what `p11296`'s
    marker was really covering: it named `falling.drop(forced_flight=)`,
    the fall at the end, inside a row that did not exist. `Summon.commands`
    now carries both, and `d2899ec7`'s convention is what makes a command a
    row -- so granting and aiming this is the same as any other.

    The ally is chosen **before** the angel moves, because the card says
    *"one ally adjacent to it"* -- adjacent now, not wherever the angel
    ends up.

    *"Must land ... or he or she falls"* is written as what it says: the
    lent flight is ended and the ally comes down. **On flat ground that
    fall is harmless and that is correct** -- `c.fall` defaults to the
    creature's own height, which `c.move` does not raise, so an ally
    carried across a flat board lands safely. It bites where something has
    lifted the ally: `falling.lift` assigns `floor + squares` and a
    level-13 controller row uses it.

    So `falling.drop(forced_flight=)` was not needed. The gap the marker
    named is real but belongs to `movement.settle`, which spares a flier at
    turn end -- *"a flyer is not settled; it is where it means to be"* --
    and that is a different sentence from this card's. Here the row ends
    the carry itself, which is what *"at the end of this movement"* means.

    A creature with a fly speed of its own is not carved out, because the
    printed sentence does not carve it out."""
    mates = sorted(a for a in c.allies() if c.adjacent_to(c.me, a))
    pick = c.choose(mates, f"{c.ref}: which ally flies with it") if mates else None
    c.move(8, who=c.me)
    if pick is None:
        return
    lent = c.mode("fly", 8, on=pick, until=When.EOT)
    c.move(8, who=pick)
    if lent is not None:
        c.end_effect(lent, on=pick, why="the flight ends")
    c.fall(on=pick)
