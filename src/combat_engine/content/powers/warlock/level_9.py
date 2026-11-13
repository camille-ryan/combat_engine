"""Warlock, level 9: the daily attacks.

Two of the four print the shape `level_5.py` sets out: an effect the target
carries and a minor action, once per round, starting on the caster's next
turn. That is a `sustain_cost` on the effect, which `actions._sustaining`
offers exactly once a round and never on the turn it was applied, and
`c.on_sustain` is the payout.

`p1408`'s effect ends by being counted rather than by a clock: five
instances of the target rolling an attack, rolling a save, or taking damage.
The three watchers hang off the effect itself so they die with it, and the
vulnerability -- which `c.vulnerable` holds as its own effect -- is ended
from the same place.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    DAILY,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackRolled,
    Cast,
    DamageApplied,
    DamageType,
    Dropped,
    Keyword,
    Mod,
    Ranged,
    SavingThrow,
    Summon,
    When,
    get,
    power,
    spread,
)
from combat_engine.engine.events import MoveEnd

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _yank(c: Cast, victim: int) -> bool:
    """Teleport the victim to an unoccupied square within 3 of the warlock.

    The printed distance is measured from the caster and `c.teleport`
    measures its own from the mover, so the allowance handed to it is the gap
    between the two plus those three squares.
    """
    room = sorted(
        sq
        for sq in spread({c.here}, 3)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    where = c.choose(room, "where it lands")
    if where is None:
        return False
    return c.teleport(c.distance(victim) + 3, who=victim, to=where)


@power(
    "p1314",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=WILL),
)
def p1314(c: Cast) -> None:
    """"Within range but not necessarily within line of sight" is what the
    longhand `c.attack` buys: it is the header's ten squares without the
    header's targeting, which would refuse a creature it cannot see.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.con_mod, dtype=DamageType.PSYCHIC)
        if victim is not None:
            _yank(c, victim)
    if victim is None:
        return
    leash = c.world.effects.apply(
        victim, c.me, When.ENCOUNTER, label=c.ref, sustain_cost=MINOR
    )

    def again() -> None:
        if c.distance(victim) > 10:
            return
        if c.attack(c.con_, WILL, on=victim):
            _yank(c, victim)
        else:
            c.world.effects.end(leash, "the attack missed")

    c.on_sustain(leash, again)


@power(
    "p1408",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p1408(c: Cast) -> None:
    """The two penalties go on one effect rather than two: they are one
    printed sentence and they have to stop together, and there is no save to
    keep them in step if they are separate.
    """
    victim = c.target
    landed = c.strike()
    if landed:
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return

    fates = c.world.effects.apply(
        victim,
        c.me,
        When.ENCOUNTER,
        label=f"{c.ref} five fates",
        mods=[
            (victim, Mod(what="attack", value=-4, kind="untyped", label=c.ref)),
            (victim, Mod(what="save", value=-4, kind="untyped", label=c.ref)),
        ],
    )
    weak = c.vulnerable(5, until=When.ENCOUNTER, on=victim)
    if weak is not None:
        fates.on_end.append(lambda: c.world.effects.end(weak, "the fates ran out"))

    left = [5 if landed else 2]

    def tick() -> None:
        if left[0] <= 0:
            return
        left[0] -= 1
        if left[0] <= 0:
            c.world.effects.end(fates, "five instances")

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == victim:
            tick()

    def saved(ev: SavingThrow) -> None:
        if ev.actor == victim:
            tick()

    def hurt(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0:
            tick()

    fates.subs.extend(
        [
            c.world.bus.on(AttackRolled, swung),
            c.world.bus.on(SavingThrow, saved),
            c.world.bus.on(DamageApplied, hurt),
        ]
    )


@power(
    "p1473",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p1473(c: Cast) -> None:
    if c.strike():
        c.damage("3d10", c.con_mod)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d10", c.con_mod)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p1474",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p1474(c: Cast) -> None:
    """"The first time the target moves on each of its turns" is one bite per
    turn, latched on whose turn it is rather than on the round: a creature
    shoved on somebody else's turn has not moved on its own.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    frost = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, sustain_cost=MINOR
    )
    c.on_sustain(frost, lambda: c.flat(10, dtype=DamageType.COLD, on=victim))

    bitten: list[tuple[int, int | None]] = []

    def stepped(ev: MoveEnd) -> None:
        now = (c.world.round, c.turn_of())
        if ev.actor != victim or c.turn_of() != victim or now in bitten:
            return
        bitten.append(now)
        c.damage("1d8", dtype=DamageType.COLD, on=victim)

    frost.subs.append(c.world.bus.on(MoveEnd, stepped))


@power(
    "p13649",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.SUMMONING],
    summon=Summon(),
)
def p13649(c: Cast) -> None:
    """Which creature arrives is the pact's, and the pacts' creatures ARE
    given -- this note used to say they were not.

    Fourteen class-feature rows print *"you can use `p13649` to summon a
    <creature>"*, one per pact, on the binder's `-f12` and the hexblade's
    `-f7`. Every one of them was marked `defect=` *"an associate and not a
    monster, so there is no stat block the summon can field"*, and all
    three clauses of that were false:

    * the compendium's `Associate` table carries the whole block -- *"HP
      your bloodied value; Defenses your defenses + 2; Speed land 8"* and
      an attack line;
    * `etl/build.py` imports it, into `associate`, with `hp`, `defences`,
      `speed` and `size` parsed out;
    * and `c.summon` has routed an `x10_` ref to
      `loader.spawn_associate` since `#459`. Measured: all seven of the
      creatures below spawn, each at the summoner's bloodied value.

    So the creature is read off what the character was dealt. `c.feat` on
    the sub-option rather than `c.chosen_option` on the parent, for two
    reasons: the parent grants the option it drew, so the sub-option IS in
    `Powers.known`; and `lint.py` requires an `implemented_in=` pointer's
    target to name the ref in its own source, which a dict-driven loop
    does not. The binder and the hexblade print the same seven creatures,
    so each branch names both refs. `#1268`.

    **The inline default is kept as the fallback**, not removed: two of
    the nine options on each chassis name a creature that resolves to no
    `Associate` row at all, and those two keep their marker. A pact with
    no recorded creature gets the generic summon it got before, which is
    the printed *"the summoned creature uses your defences"* reading.

    "Or hit points equal to your surge value if you have no surges left" is the
    fallback when `c.spend_surge` comes back False. Dropped: dismissing it as a
    minor action, which would be a second row and the spec names no id for
    one."""
    beast = ""
    if c.feat("cf:warlock-binder-f12s0") or c.feat("cf:warlock-hexblade-f7s0"):
        beast = "x10_82"
    elif c.feat("cf:warlock-binder-f12s1") or c.feat("cf:warlock-hexblade-f7s1"):
        beast = "x10_21"
    elif c.feat("cf:warlock-binder-f12s4") or c.feat("cf:warlock-hexblade-f7s4"):
        beast = "x10_6"
    elif c.feat("cf:warlock-binder-f12s5") or c.feat("cf:warlock-hexblade-f7s5"):
        beast = "x10_25"
    elif c.feat("cf:warlock-binder-f12s6") or c.feat("cf:warlock-hexblade-f7s6"):
        beast = "x10_8"
    elif c.feat("cf:warlock-binder-f12s7") or c.feat("cf:warlock-hexblade-f7s7"):
        beast = "x10_10"
    elif c.feat("cf:warlock-binder-f12s8") or c.feat("cf:warlock-hexblade-f7s8"):
        beast = "x10_19"
    made = (c.summon(beast, at=c.origin, after=c.me) if beast
            else c.summon_inline(get(c.ref).summon, at=c.origin))
    if not made:
        return

    def pay(ev: Dropped) -> None:
        if ev.actor == made and not c.spend_surge(on=c.me):
            c.flat(c.surge_value(), on=c.me)

    c.watch(Dropped, pay, until=When.ENCOUNTER)
