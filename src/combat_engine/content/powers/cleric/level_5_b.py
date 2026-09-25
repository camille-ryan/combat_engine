"""Cleric, level 5: the daily attacks printed after the first book.

`level_5.py` holds the four that came first; these are the rest.

Two rows name something the model does not hold and are written round it.
`p11619` blesses *a weapon*, and a weapon is not an entity here -- so, as
`p1406` in the other file already decided, the blessing rides on whoever is
holding it and reads the wielder's weapon attacks off the row that made
them. `p9984` pays out "when you use a Channel Divinity or healing word
power", and neither of those is a thing a header can say: what they have in
common structurally is that they are the cleric's **level 0** rows, so that
is what the watch asks. A row added to that set later is picked up for free,
which is the right failure direction.

`p7091` is the only escalating modifier in the batch. Its `Mod` is built by
hand and kept, because the printed line worsens the same penalty rather than
laying a second one -- and two penalties would stack to something the -10
floor could not hold.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Mod,
    Position,
    PowerUsed,
    Ranged,
    Relation,
    SavingThrow,
    When,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.query import team

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _weapon_row(ref: str) -> bool:
    """Was that attack a weapon attack? Read off the row that made it."""
    row = get(ref) if ref else None
    return row is not None and Keyword.WEAPON in row.keywords


def _melee_row(ctx: dict[str, Any]) -> bool:
    """Gate a damage modifier on "melee damage rolls".

    The damage context carries the row's id and nothing about its shape, and
    most melee rows carry no melee *keyword*, so the reach is looked up.
    """
    row = get(ctx.get("power") or "")
    return row is not None and row.reach is not None and row.reach.kind == "melee"


@power(
    "p11619",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p11619(c: Cast) -> None:
    """A weapon is not an entity, so the row is aimed at whoever holds it.

    The combat advantage is applied with the *wielder* as its source: the
    printed duration is measured off the wielder's next turn and a duration
    is clocked by the effect's source, which is usually somebody else. The
    printed line names nobody it is granted to, so it goes to the wielder's
    whole side.
    """
    wielder = c.target
    if wielder is None:
        return
    c.bonus(
        "damage",
        c.str_mod,
        on=wielder,
        until=When.ENCOUNTER,
        kind="power",
        when=lambda ctx: _weapon_row(ctx.get("power") or ""),
    )

    def opened(ev: Hit) -> None:
        if ev.attacker != wielder or not _weapon_row(ev.power):
            return
        if team(c.world, ev.target) is team(c.world, wielder):
            return
        friends = sorted({c.me, wielder, *c.allies()})
        c.world.effects.apply(
            ev.target,
            wielder,
            When.SONT,
            label=f"{c.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, ev.target, f) for f in friends],
        )

    c.watch(Hit, opened, until=When.ENCOUNTER, on=wielder, label=c.ref)


@power(
    "p12411",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p12411(c: Cast) -> None:
    """The burn and the attack penalty are one hold, so one saving throw
    lifts both -- and that same saving throw is the last thing the hold
    charges for, which is what "including the save against this power"
    means. `Effects.save` announces the throw before acting on it, so the
    listener is still subscribed when the successful one is read.
    """
    c.grants_advantage(until=When.EONT, to="allies")
    if not c.strike():
        return
    victim = c.target
    burn = 5 + c.wis_mod
    hold = c.penalty("attack", 2, until=When.SAVE_ENDS)
    if hold is None:
        return

    def struck(ev: Hit) -> None:
        if ev.attacker == victim and not hold.ended:
            c.flat(burn, on=victim)

    def shrugged(ev: SavingThrow) -> None:
        if ev.actor == victim and ev.saved:
            c.flat(burn, on=victim)

    hold.subs.append(c.world.bus.on(Hit, struck, owner=c.me))
    hold.subs.append(c.world.bus.on(SavingThrow, shrugged, owner=c.me))


@power(
    "p12609",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12609(c: Cast) -> None:
    """The opening is offered on the declaration rather than on the hit,
    which is where an opportunity attack interrupts: the printed line makes
    swinging at the party cost the target a swing back whether or not the
    blow lands."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    me = c.me

    def opening(ev: AttackDeclared) -> None:
        if ev.target == me or ev.target in c.allies():
            c.provoke(me, on=victim, why=c.ref)

    c.on_attack(opening, by=victim, until=When.ENCOUNTER, label=c.ref)


@power(
    "p12610",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12610(c: Cast) -> None:
    """Both halves of the Effect are printed "can", so both are asked, and
    the swing is only offered to an ally whose shift actually finished next
    to the target.

    The destination is offered rather than left to `c.shift`'s own decider,
    and offered nearest the target first: `World.decide` takes the head of
    the list when nobody is playing, and the untouched order is the
    lowest-sorted square, which walked every ally out of reach of the second
    half of its own line.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    where = c.there
    for friend in sorted(f for f in c.within(2, side="ally") if f != c.me):
        if not c.may("shift up to 2 squares", who=friend):
            continue
        room = sorted(
            c.world.reachable_squares(friend, 2),
            key=lambda sq: (distance(sq, where), sq),
        )
        spot = c.choose(room, "where the ally shifts to") if room else None
        if spot is not None:
            c.shift(2, who=friend, to=spot)
        if c.adjacent_to(victim, friend) and c.may("swing at the target", who=friend):
            c.grant_attack(friend, on=victim)


@power(
    "p3634",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p3634(c: Cast) -> None:
    """"Save ends both" is one hold carrying two conditions, not two holds:
    two would give the target two throws and let it shake off half."""
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.wis_mod)
        c.slowed(until=When.EONT)


@power(
    "p3635",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p3635(c: Cast) -> None:
    """The Effect line lands whether or not the attack did, which is why the
    burn sits outside the branch.

    "Ignores concealment and cover" is half a sentence here: `ignore_cover`
    is the cover, and concealment is not a thing the engine models at all.
    The other rider -- the target cannot become hidden -- has no spelling
    either, so a target of this can still hide.
    """
    if c.strike(ignore_cover=True):
        c.damage("3d6", c.wis_mod, dtype=DamageType.RADIANT)
    c.ongoing(5, DamageType.RADIANT, until=When.SAVE_ENDS)


@power(
    "p7089",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING, Keyword.TELEPORTATION],
    attack=Attack(STR, vs=AC),
)
def p7089(c: Cast) -> None:
    """The ally arrives in a named square, so the teleport is given one --
    left to the decider it would blink somewhere merely legal. Its distance
    is measured rather than guessed, because `c.teleport` will only accept a
    destination inside the range it is handed.

    The surge is owed whether or not there was anywhere to arrive.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return
    friends = sorted(f for f in c.within(5, side="ally") if f != c.me)
    friend = c.choose(friends, "who blinks in") if friends else None
    if friend is None:
        return
    landing = sorted(
        sq
        for sq in spread({c.there}, 1) - {c.there}
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    spot = c.choose(landing, "where the ally arrives") if landing else None
    standing = c.world.get(friend, Position)
    if spot is not None and standing is not None:
        far = max(1, distance(standing.square, spot))
        if c.teleport(far, who=friend, to=spot):
            c.grant_attack(friend, on=victim)
    if c.may("spend a healing surge", who=friend):
        c.surge(on=friend)


@power(
    "p7090",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RELIABLE],
    attack=Attack(WIS, vs=REF),
)
def p7090(c: Cast) -> None:
    """One hold carries the attack penalty and the -2 to shake it off, which
    is why it is built here rather than through `c.penalty`: `save_mod` is a
    property of the effect and there is nowhere to put it on a bare modifier.

    The daze answers `AttackRolled` rather than the declaration, the printed
    line being "after the target attacks".
    """
    if not c.strike():
        return
    victim = c.target
    hold = c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, Mod(what="attack", value=-4, kind="untyped", label=c.ref))],
        save_mod=-2,
    )

    def reels(ev: AttackRolled) -> None:
        if ev.attacker != victim or hold.ended:
            return
        if ev.target == c.me or ev.target in c.allies():
            c.dazed(on=victim, until=When.EOTNT)

    hold.subs.append(c.world.bus.on(AttackRolled, reels, owner=c.me))


@power(
    "p7091",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p7091(c: Cast) -> None:
    """Hit and miss are the same arrangement at different numbers, so the
    row is written once with three of them.

    The modifier is mutated in place. Laying a fresh penalty each time would
    stack -- penalties always do -- and reach the floor after two swings
    instead of three.
    """
    victim = c.target
    if victim is None:
        return
    start, step, floor = (4, 2, 10) if c.strike() else (2, 1, 5)
    blunted = Mod(
        what="damage", value=-start, kind="untyped", when=_melee_row, label=c.ref
    )
    hold = c.world.effects.apply(
        victim, c.me, When.ENCOUNTER, label=c.ref, mods=[(victim, blunted)]
    )

    def worsens(ev: Hit) -> None:
        if ev.attacker == victim and _melee_row({"power": ev.power}):
            blunted.value = max(-floor, blunted.value - step)

    hold.subs.append(c.world.bus.on(Hit, worsens, owner=c.me))


@power(
    "p9984",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9984(c: Cast) -> None:
    """The two kinds of power the Effect names are the cleric's class
    features, and a header has no field that says so. What they do have in
    common is their level: they are the rows the class brings with it at
    level 0, which is also what the audit board hands a caster. So the watch
    asks the row's level and class rather than a list of ids -- a list would
    go stale the moment another feature is written.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return

    def answered(ev: PowerUsed) -> None:
        row = get(ev.power)
        if ev.actor != c.me or row is None or row.level != 0 or row.cls != "cleric":
            return
        c.flat(c.cha_mod, on=victim)
        for friend in c.within(1, side="ally"):
            c.temp_hp(c.cha_mod, on=friend)

    c.watch(PowerUsed, answered, until=When.ENCOUNTER, label=c.ref)
