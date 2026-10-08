"""Fourteen themes: x7_642, x7_670, x7_872, x7_860, x7_874, x7_921, x7_923,
x7_941, x7_949, x7_980, x7_990, x7_997, x7_1003, x7_1015.

Two things recur across the batch and are decided once here.

**"Primary ability vs. X".** A theme does not know which class took it, so
the printed attack line names no ability and `Attack` has nowhere to put
one: `Attack.bonus_for` raises without either an ability or a printed
bonus, and `Power.hit_chance` calls it, so a header declared that way takes
the AI policy down. Every such row carries `c.ability_for(ref)` as a
`todo=` -- there is no ability to guess at and the whole row hangs off it.

**"Highest ability modifier vs. X"** is a different sentence and is
sayable. Half level, proficiency and enhancement are common to all six
abilities, so the largest of `c.str_ .. c.cha_` is the same number the
printed line means. Those rows roll in the body with `c.attack` and
declare no `attack=`; the header loses its data, which is the cost of the
engine having no way to spell the line.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AdjacencyGained,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    ForcedMove,
    Health,
    Hit,
    Initiative,
    InitiativeRolled,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    Pick,
    PowerUsed,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    World,
    ZoneEntered,
    about_me,
    both,
    by_charge,
    by_keyword,
    by_me,
    by_melee,
    by_ranged,
    closed_on_me,
    either,
    get,
    power,
    targets_me,
)
from combat_engine.engine.grid import Square, spread
from combat_engine.engine.skills import SKILLS

#: The unnamed attack ability. See the module docstring.
ABILITY = ("c.ability_for(ref)",)

#: Where `_enhanced` remembers its answer for the rest of one use.
_ENHANCED = "_x7_670_enhanced"

#: "a -N penalty to opportunity action **and immediate action** attack
#: rolls". The attack context carries `opportunity`, so the first half is a
#: gate; nothing on it says an attack was an interrupt or a reaction, so the
#: second half has no key to read.
IMMEDIATE = ("resolve.attack(immediate=)",)

MARTIAL = [Keyword.MARTIAL]
ARCANE = [Keyword.ARCANE]
SHADOW = [Keyword.SHADOW]
DIVINE = [Keyword.DIVINE]


def _best(c: Cast) -> int:
    """"Highest ability modifier vs. X", as an attack bonus."""
    return max(c.str_, c.con_, c.dex_, c.int_, c.wis_, c.cha_)


def _best_mod(c: Cast) -> int:
    """"+ your highest ability modifier", on the damage line."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _half_speed(c: Cast, who: int) -> int:
    return max(1, c.speed_of(who) // 2)


def _bloodied(world: World, eid: int) -> bool:
    """"Requirement: You must be bloodied"."""
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _rolled(world: World, eid: int) -> int:
    init = world.get(eid, Initiative)
    return 0 if init is None else init.rolled


def _enhanced(c: Cast) -> bool:
    """"Special: You can spend a minor action when you use this power to
    enhance it." Every x7_670 attack row prints one, each naming a different
    enhancement.

    Asked **once per use** rather than once per target. The minor is one
    action, and a close burst 5 would otherwise offer to buy it again for
    every enemy it caught. The answer is remembered on the cast, which works
    because `dsl.use` hands the *same* `Cast` to each target -- it rebinds
    `target` and `index` on one object, which is what makes `c.first` mean
    anything -- so an attribute set on the first pass is still there on the
    last.

    `default=True`: a minor spent on a strict upgrade is nearly always right,
    and `c.may`'s first option is the answer in every headless fight.
    """
    held = getattr(c, _ENHANCED, None)
    if held is not None:
        return bool(held)
    enc = c.world.encounter
    yes = bool(
        enc is not None
        and enc.can_spend(c.me, ActionType.MINOR)
        and c.may("spend a minor action to enhance it")
        and enc.spend(c.me, ActionType.MINOR)
    )
    setattr(c, _ENHANCED, yes)
    return yes


def _unless_adjacent(
    c: Cast, foe: int, who: int
) -> Callable[[dict[str, Any]], bool]:
    """"All creatures that are not adjacent to it have concealment against
    it."

    Concealment is laid on the creature that has it and gated on the attack
    context, which is the idiom `c.conceal`'s own docstring gives for
    "concealment from creatures more than 3 squares away". So this is one
    effect per creature, reading `attacker` to narrow it to the restrained
    one, and re-asking adjacency on every roll rather than closing over who
    was adjacent when the burst went off.

    Laid the other way round -- as a penalty on the restrained creature's
    own attacks -- it would be one effect covering anything that arrives
    later, but concealment and cover take the **larger** of the two and an
    attack penalty adds to both, so a target behind cover would be two
    points harder to hit than the card allows.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") == foe and who not in c.within(1, of=foe)

    return gate


def _vs_opportunity(ctx: dict[str, Any]) -> bool:
    """"Against opportunity attacks": the attack context carries the flag."""
    return bool(ctx.get("opportunity"))


def _baited(c: Cast, foe: int, punish: Callable[[], None]) -> None:
    """"Until the end of your next turn, if the target willingly moves more
    than 2 squares or makes an attack, ..." -- three rows of x7_642 print it
    and differ only in what follows.

    **"Willingly" is the `MoveStart` bracket, and `Moved` alone is not it.**
    `movement.forced` steps through `movement.step` like everything else, and
    `step` announces a `Moved` with `kind_` set to "push" -- so counting
    `Moved` by itself makes a shove count against the target, which is the
    one thing the word "willingly" is there to exclude. Only `walk`, `run`,
    `shift` and `teleport` announce a `MoveStart`, so the squares entered
    between one and its `MoveEnd` are the willing ones. `p7014` counts the
    same way and its module docstring is where this is written down.

    Counted **across the whole duration** rather than per move: the card says
    "moves more than 2 squares" and does not say "in a single move", which is
    the narrower reading two other rows in the tree take because their cards
    say "in a single move". It fires once either way.

    The attack half watches `PowerUsed` and not `AttackDeclared`, because an
    attack is announced once per *target*: a burst would otherwise be several
    attacks and the distinction never matters here, but `AttackDeclared`
    would also miss a row that declares an attack it never rolls.
    """
    hold = c.effect(f"{c.ref} bait", until=When.EONT, on=foe)
    if hold is None:
        return
    walking = [False]
    steps = [0]
    done = [False]

    def fire() -> None:
        if done[0]:
            return
        done[0] = True
        punish()

    def opened(ev: MoveStart) -> None:
        if ev.actor == foe:
            walking[0] = True

    def closed(ev: MoveEnd) -> None:
        if ev.actor == foe:
            walking[0] = False

    def stepped(ev: Moved) -> None:
        if ev.actor != foe or not walking[0]:
            return
        steps[0] += 1
        if steps[0] > 2:
            fire()

    def swung(ev: PowerUsed) -> None:
        row = get(ev.power) if ev.actor == foe else None
        if row is not None and row.is_attack:
            fire()

    bus = c.world.bus
    hold.subs.append(bus.on(MoveStart, opened, window=Window.BEFORE, owner=c.me))
    hold.subs.append(bus.on(Moved, stepped, owner=c.me))
    hold.subs.append(bus.on(MoveEnd, closed, owner=c.me))
    hold.subs.append(bus.on(PowerUsed, swung, owner=c.me))


# ==========================================================================
# x7_642 -- a martial theme; its rows deal poison
# ==========================================================================


@power(
    "p11749",
    level=0,
    cls="x7_642",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11749(c: Cast) -> None:
    """1[W] plus 5 poison, and a trip that waits for the target to move or
    swing.

    **No ability modifier on the damage line**, which is the card and not an
    omission: this one prints "1[W] damage plus 5 poison damage" while the
    level 9 row of the same theme prints "2[W] + ability modifier", so the
    absence is deliberate where it appears.

    The two amounts are dealt as two blows because the card prints them as
    two amounts of two types -- poison resistance takes the second and has
    no claim on the first.
    """
    if not c.strike():
        return
    c.damage(c.w(1))
    c.flat(5, dtype=DamageType.POISON)
    foe = c.target
    if foe is None:
        return

    def trip() -> None:
        c.prone(on=foe)
        c.immobilized(until=When.EOTNT, on=foe)

    _baited(c, foe, trip)


@power(
    "p11750",
    level=2,
    cls="x7_642",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    todo=("c.advantage_on_roll()",),
)
def p11750(c: Cast) -> None:
    """An invisible weapon has no combat consequence of its own; the whole
    row is the combat advantage it buys on one future attack, and nothing
    holds combat advantage for an attack that has not been declared."""
    ...


@power(
    "p11751",
    level=3,
    cls="x7_642",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11751(c: Cast) -> None:
    """The level 0 row one step up: 2[W], and the bait pays a daze."""
    if not c.strike():
        return
    c.damage(c.w(2))
    c.flat(5, dtype=DamageType.POISON)
    foe = c.target
    if foe is None:
        return
    _baited(c, foe, lambda: c.dazed(until=When.EOTNT, on=foe))


@power(
    "p11754",
    level=5,
    cls="x7_642",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[
        Keyword.MARTIAL, Keyword.WEAPON, Keyword.POISON, Keyword.RELIABLE,
    ],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11754(c: Cast) -> None:
    """A poison burn, and a -4 on the one saving throw that follows its first
    tick.

    **The penalty goes on the burn's own `save_mod`, not on a `"save"`
    modifier.** The printed line narrows it to saves *against the ongoing
    damage*, and a modifier under that key applies to every save the creature
    makes -- including the one that would end an unrelated hold.

    It is handed back inside the `SavingThrow` listener. `Effects._on_turn_end`
    computes `bonus` before it announces the event, so the roll being
    announced has already had the -4 and the next one has not.

    Tied to the tick rather than laid up front. The two are equivalent today
    because ongoing damage is dealt at the start of a turn and the save is
    made at its end, so the first save always follows the first tick -- but
    that is an ordering, not the sentence the card prints.
    """
    if not c.strike():
        return
    c.damage(c.w(2))
    foe = c.target
    if foe is None:
        return
    c.slowed(until=When.SOTNT)
    burn = c.ongoing(5, DamageType.POISON)
    if burn is None:
        return
    burned = [False]
    spent = [False]

    def ticked(ev: DamageApplied) -> None:
        if burned[0] or ev.target != foe or ev.detail != str(burn):
            return
        burned[0] = True
        burn.save_mod -= 4

    def rolled(ev: SavingThrow) -> None:
        if not burned[0] or spent[0] or ev.actor != foe:
            return
        if ev.against != str(burn):
            return
        spent[0] = True
        burn.save_mod += 4

    bus = c.world.bus
    burn.subs.append(bus.on(DamageApplied, ticked, owner=c.me))
    burn.subs.append(bus.on(SavingThrow, rolled, owner=c.me))


@power(
    "p11762",
    level=6,
    cls="x7_642",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p11762(c: Cast) -> None:
    """Coat the weapon; the next creature hit by a *melee* attack with it
    takes the vulnerability.

    `c.apply_poison(once=True)` would spend the coating on a thrown hit
    with the same weapon, which the printed line does not, so the hold is
    kept open and the melee test is made inside the bite.
    """
    spent: list[int] = []

    def bite(ev: Hit) -> None:
        if spent or not by_melee(c.world, c.me, ev):
            return
        spent.append(1)
        c.vulnerable(5, DamageType.POISON, on=ev.target, until=When.EONT)

    c.apply_poison(bite, until=When.ENCOUNTER, once=False)


@power(
    "p11763",
    level=7,
    cls="x7_642",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11763(c: Cast) -> None:
    """The same bait again, paying weakened."""
    if not c.strike():
        return
    c.damage(c.w(2))
    c.flat(5, dtype=DamageType.POISON)
    foe = c.target
    if foe is None:
        return
    _baited(c, foe, lambda: c.weakened(until=When.EOTNT, on=foe))


@power(
    "p11766",
    level=9,
    cls="x7_642",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[
        Keyword.MARTIAL, Keyword.WEAPON, Keyword.POISON, Keyword.RELIABLE,
    ],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11766(c: Cast) -> None:
    """A poison burn that cannot be shrugged off on the turn it first bites.

    **`c.unsave` is the wrong verb.** It makes the save *fail*, and a failed
    save is what runs an effect's `escalate`; "cannot make a saving throw" is
    the save not happening at all. `Effects._on_turn_end` reads
    `rolled.cancelled` and leaves the effect exactly as it was, which is the
    printed outcome, so this cancels the `SavingThrow` instead.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.attack_mod)
    foe = c.target
    if foe is None:
        return
    burn = c.ongoing(5, DamageType.POISON)
    if burn is None:
        return
    burned = [False]
    blocked = [False]

    def ticked(ev: DamageApplied) -> None:
        if burned[0] or ev.target != foe or ev.detail != str(burn):
            return
        burned[0] = True

    def rolled(ev: SavingThrow) -> None:
        if not burned[0] or blocked[0] or ev.actor != foe:
            return
        if ev.against != str(burn):
            return
        blocked[0] = True
        ev.cancel("cannot save against it this turn")

    bus = c.world.bus
    burn.subs.append(bus.on(DamageApplied, ticked, owner=c.me))
    burn.subs.append(bus.on(SavingThrow, rolled, owner=c.me))


@power(
    "p11769",
    level=10,
    cls="x7_642",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    todo=("c.area_origin()",),
)
def p11769(c: Cast) -> None:
    """The stance's whole content is moving the square a weapon attack is
    measured from. `c.strike(from_=)` says it for one swing and nothing
    holds it for a duration."""
    ...


# ==========================================================================
# x7_670 -- an arcane misdirector
# ==========================================================================


@power(
    "p12338",
    level=0,
    cls="x7_670",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12338(c: Cast) -> None:
    """Psychic damage, and somebody on your side drops out of that
    creature's sight.

    `side="team"` and not `"ally"`: the card says "you **or** one ally", and
    `"ally"` deliberately leaves the caster out.

    The Special's slide is bought before the attack is rolled and paid for
    either way, which is what "when you use this power" says -- the minor
    buys the enhanced version of the card, not a hit.
    """
    better = _enhanced(c)
    if not c.strike():
        return
    c.damage("1d10", c.attack_mod, dtype=DamageType.PSYCHIC)
    foe = c.target
    if foe is None:
        return
    if better:
        c.slide(1)
    who = c.choose(c.within(10, side="team"), "who it cannot see")
    if who is not None:
        c.invisible(to=foe, on=who, until=When.EONT)


@power(
    "p12339",
    level=2,
    cls="x7_670",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    todo=("c.advantage_on_roll()",),
)
def p12339(c: Cast) -> None:
    """Combat advantage held for one future arcane attack: the grant names
    no creature to have it against, which is the half `c.grants_advantage`
    cannot express."""
    ...


@power(
    "p12340",
    level=3,
    cls="x7_670",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(Pick.PRIMARY, vs=FORT),
    dropped=IMMEDIATE,
)
def p12340(c: Cast) -> None:
    """A shift either side of the blast, then slowed and clumsy out of turn.

    "Before or after the attack" is a choice with nowhere to be offered: the
    body runs once the blast's targets are already chosen, so after is the
    half that survives, and `c.first` keeps it to one shift for the whole
    blast rather than one per enemy caught.

    **The Special is deliberately not offered here**, alone in this theme.
    It reads "the target cannot make opportunity attacks or immediate action
    attacks *instead of* taking a penalty to attack rolls", so taking it
    trades the penalty below for a clause the engine cannot say -- the minor
    would be spent to make the row do less. Both halves want the same missing
    thing, which is why one symbol covers the row.
    """
    if c.first:
        c.shift(3)
    if not c.strike():
        return
    c.damage("1d8", c.attack_mod, dtype=DamageType.RADIANT)
    c.slowed(until=When.EONT)
    c.penalty("attack", 4, until=When.EONT, when=_vs_opportunity)


@power(
    "p12341",
    level=5,
    cls="x7_670",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
    dropped=IMMEDIATE,
    narrative=("skill:arcana",),
)
def p12341(c: Cast) -> None:
    """Psychic damage and a deafening, with the attack penalty on the same
    saving throw.

    **"Save ends both" is one roll, so it has to be one clock.** The penalty
    is laid `until=When.ENCOUNTER` -- where a save-ends effect ends up anyway
    if nothing ever saves -- and the deafening's `on_end` takes it away, so
    the single save clears the pair. Two save-ends effects would be two rolls
    and the card prints one.

    The Special -- 5 psychic each time it fails a saving throw against this
    power -- is `Effect.escalate`, which is run by `Effects._on_turn_end` on
    exactly a failed save and not on a cancelled one.

    The Miss clause's other half is a -2 to any check made to work out what
    you did. That is an arcana check about a circumstance, and nothing on a
    board rolls one, so the penalty has nowhere to go and nothing is missing.
    """
    better = _enhanced(c)
    if not c.strike():
        c.half_damage("1d10", c.attack_mod, dtype=DamageType.PSYCHIC)
        return
    c.damage("1d10", c.attack_mod, dtype=DamageType.PSYCHIC)
    foe = c.target
    if foe is None:
        return
    hold = c.condition(
        Condition.DEAFENED,
        until=When.SAVE_ENDS,
        escalate=(
            (lambda _eff: c.flat(5, dtype=DamageType.PSYCHIC, on=foe))
            if better
            else None
        ),
    )
    pen = c.penalty("attack", 2, until=When.ENCOUNTER, when=_vs_opportunity)
    if hold is not None and pen is not None:
        hold.on_end.append(lambda: c.end_effect(pen))


@power(
    "p12342",
    level=6,
    cls="x7_670",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    dropped=("c.extend_shift()",),
)
def p12342(c: Cast) -> None:
    """The concealment half is exact and hangs off the shift actually
    happening; the two extra squares of that shift have nothing to hold
    them."""
    who = c.target
    if who is None:
        return
    done: list[int] = []

    def shifted(ev: Moved) -> None:
        if done or ev.actor != who or getattr(ev, "kind_", "") != "shift":
            return
        done.append(1)
        c.conceal(on=who, until=When.EOTNT)

    c.watch(Moved, shifted, until=When.EONT)


@power(
    "p12343",
    level=7,
    cls="x7_670",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[
        Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(Pick.PRIMARY, vs=REF),
)
def p12343(c: Cast) -> None:
    """Psychic damage, and the target cannot see past two squares.

    The move is `c.first` for the same reason as `p12340`'s, and after the
    attack for the same reason. The Special turns it into a teleport, which
    is the whole of the enhancement.
    """
    better = _enhanced(c)
    if c.first:
        c.teleport(2) if better else c.shift(2)
    if not c.strike():
        return
    c.damage("1d10", c.attack_mod, dtype=DamageType.PSYCHIC)
    c.sight_range(2, until=When.EONT)


@power(
    "p12344",
    level=9,
    cls="x7_670",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=FORT),
    dropped=("c.forbid(keyword=)",),
)
def p12344(c: Cast) -> None:
    """Restrained, and half-blind while it is.

    The concealment hangs off the restraint's `on_end` so that the one save
    the card prints clears all of it -- see `p12341` for why, and
    `_unless_adjacent` for why it is laid one creature at a time.

    The Special is a -2 to saving throws against this power, which is the
    hold's own `save_mod` -- narrowed to this effect, where a `"save"`
    modifier would apply to every roll the creature made.

    "The target cannot teleport" is the dropped half: `c.forbid` takes one
    row's ref, and this forbids every row carrying a keyword.
    """
    better = _enhanced(c)
    if not c.strike():
        c.half_damage("2d6", c.attack_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.SAVE_ENDS)
        return
    c.damage("2d6", c.attack_mod, dtype=DamageType.PSYCHIC)
    foe = c.target
    if foe is None:
        return
    hold = c.condition(
        Condition.RESTRAINED, until=When.SAVE_ENDS, save_mod=-2 if better else 0
    )
    if hold is None:
        return
    for other in c.within(30, of=foe, side="other"):
        veil = c.conceal(
            on=other, until=When.ENCOUNTER, when=_unless_adjacent(c, foe, other)
        )
        if veil is not None:
            hold.on_end.append(lambda v=veil: c.end_effect(v))


@power(
    "p12345",
    level=10,
    cls="x7_670",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE,
    todo=("c.see_from(who)",),
)
def p12345(c: Cast) -> None:
    """Seeing and hearing from another creature's square is not narrative
    -- line of sight is what an attack is measured with -- and nothing
    moves where a creature's senses sit. `c.sight_range` changes how far,
    not from where."""
    ...


# ==========================================================================
# x7_872 -- a martial survivor
# ==========================================================================


@power(
    "p14209",
    level=2,
    cls="x7_872",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you would make an Intelligence- or Wisdom-based check",
    out_of_combat=True,
)
def p14209(c: Cast) -> None:
    """Substituting one skill for another changes which check is rolled and
    never whether anything on a board happens."""


@power(
    "p14210",
    level=6,
    cls="x7_872",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are subjected to a pull, a push or a slide",
    on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"),
)
def p14210(c: Cast) -> None:
    """The surge is spent whether or not the shift finds anywhere to go --
    the card charges for the negation, not for the movement."""
    c.spend_surge(on=c.me)
    c.cancel()
    c.shift(3, who=c.me)


def _my_save_failed(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor == me and not ev.saved


@power(
    "p14211",
    level=10,
    cls="x7_872",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you fail a saving throw",
    on=Trigger(SavingThrow, _my_save_failed, "you fail a saving throw"),
    todo=("c.unsave(succeed=)",),
)
def p14211(c: Cast) -> None:
    """`c.unsave` turns a success into a failure and there is no other
    half: nothing anywhere writes `saved = True`. Spending the surge
    without the success would be a row that plays and only costs."""
    ...


# ==========================================================================
# x7_860 -- a martial rallier
# ==========================================================================


@power(
    "p14159",
    level=0,
    cls="x7_860",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(3),
    target=Target("other_ally", 2),
    keywords=MARTIAL,
)
def p14159(c: Cast) -> None:
    c.shift(2, who=c.target)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", until=When.EONT)


@power(
    "p14160",
    level=2,
    cls="x7_860",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p14160(c: Cast) -> None:
    """The bonus is laid because it can be, but the row is inert: no
    Intimidate check is rolled on a board, and standing in for a Bluff or a
    Diplomacy check is the same claim twice over."""
    c.bonus("skill:intimidate", 5, kind="power", on=c.me, until=When.ENCOUNTER)


def _my_save_succeeded(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor == me and bool(ev.saved)


@power(
    "p14161",
    level=6,
    cls="x7_860",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger="you succeed on a saving throw",
    on=Trigger(SavingThrow, _my_save_succeeded, "you succeed on a saving throw"),
)
def p14161(c: Cast) -> None:
    c.save(on=c.target, bonus=2)


def _ally_rolled_lower(world: World, me: int, ev: InitiativeRolled) -> bool:
    from combat_engine.engine.query import distance_between, team

    who = ev.actor
    if who == me or team(world, who) is not team(world, me):
        return False
    if distance_between(world, me, who) > 5:
        return False
    return _rolled(world, who) < _rolled(world, me)


@power(
    "p14162",
    level=10,
    cls="x7_860",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger="an ally rolls a lower initiative check than yours",
    on=Trigger(InitiativeRolled, _ally_rolled_lower, "an ally rolls lower"),
)
def p14162(c: Cast) -> None:
    """"Improves to" is a set, and `c.initiative` adds, so the row hands
    over exactly the gap between the two counts."""
    who = c.target
    if who is None:
        return
    gap = _rolled(c.world, c.me) - _rolled(c.world, who)
    if gap > 0:
        c.initiative(gap, on=who)


# ==========================================================================
# x7_874 -- a shadow blinker
# ==========================================================================


@power(
    "p14212",
    level=0,
    cls="x7_874",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    todo=("c.blindsight()",),
)
def p14212(c: Cast) -> None:
    """Blindsight is the whole row. `c.truesight` is a different sense and
    `c.see_invisible` is narrower than either."""
    ...


@power(
    "p14213",
    level=2,
    cls="x7_874",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    trigger="you reappear after using any teleportation power",
    on=Trigger(
        PowerUsed,
        both(about_me, by_keyword(Keyword.TELEPORTATION)),
        "you use a teleportation power",
    ),
    dropped=("c.hide(partial_cover=)",),
)
def p14213(c: Cast) -> None:
    """The three states and their "until you attack" end are exact. Hiding
    on partial cover or on cover an ally is giving you is a relaxation of
    the stealth rules and nothing holds one.

    **Re-pointed off `c.stay_hidden()`.** That symbol was doing duty for
    three different needs and one of them -- re-hiding after a missed attack
    -- is met by the `AttackDeclared` AFTER window and never wanted a verb at
    all (`f1396`). What this row waits on is permission to hide on *partial*
    cover, which is a different question from keeping hiddenness once cover
    is gone (`m5281a1`). One symbol for three needs cannot go green correctly
    for any of them. #390."""
    held = [
        c.insubstantial(on=c.me, until=When.EONT),
        c.phasing(on=c.me, until=When.EONT),
        c.vulnerable(5, DamageType.RADIANT, on=c.me, until=When.EONT),
    ]

    def ends(ev: object) -> None:
        for eff in held:
            c.end_effect(eff, on=c.me, why="attacked")

    c.on_attack(ends, by=c.me, once=True, until=When.EONT)


@power(
    "p14214",
    level=6,
    cls="x7_874",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy with an attack"),
)
def p14214(c: Cast) -> None:
    """Partial concealment is `c.conceal` untotalled."""
    c.conceal(on=c.me, until=When.EONT)
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.grants_advantage(on=who, to=c.me, until=When.EONT)


@power(
    "p14216",
    level=10,
    cls="x7_874",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    dropped=("c.grant_action('teleport')", "c.light()"),
)
def p14216(c: Cast) -> None:
    """The opening teleport is exact. The standing once-a-round 3-square
    teleport is an action `actions.legal` does not know -- `c.grant_action`
    silently eats the word -- and the dim-light restriction on both has no
    lighting to read."""
    c.teleport(6, who=c.me)


# ==========================================================================
# x7_921 -- a divine weapon-bearer
# ==========================================================================


@power(
    "p15928",
    level=0,
    cls="x7_921",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.WEAPON],
    dropped=("c.hit_this_turn()",),
)
def p15928(c: Cast) -> None:
    """Highest ability modifier vs. AC, rolled in the body -- see the
    module docstring. The Requirement is the dropped half: nothing records
    that a weapon attack landed earlier this turn, and `requires=` is
    handed a world and an eid with no turn history in it."""
    c.attack(_best(c), vs=AC)
    if c.landed:
        c.damage(c.w())


@power(
    "p15929",
    level=2,
    cls="x7_921",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    trigger="you are hit by a melee or ranged attack while holding a weapon",
    on=Trigger(
        Hit, both(targets_me, either(by_melee, by_ranged)), "you are hit"
    ),
)
def p15929(c: Cast) -> None:
    """Declared on `Hit` rather than `AttackDeclared`, because the printed
    trigger is the hit and not the swing; the bonus therefore lands on the
    defence for the rest of its printed duration rather than turning the
    triggering hit into a miss."""
    if not c.held():
        return
    defence = getattr(c.trigger, "vs", None)
    if defence is not None:
        c.bonus(defence, 2, kind="power", on=c.me, until=When.EONT)


def _my_turn(world: World, me: int, ev: TurnStart) -> bool:
    return ev.actor == me and not ev.ghost


@power(
    "p15930",
    level=6,
    cls="x7_921",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    trigger="you start your turn dominated or stunned, save ends",
    on=Trigger(TurnStart, _my_turn, "you start your turn"),
)
def p15930(c: Cast) -> None:
    for cond in (Condition.DOMINATED, Condition.STUNNED):
        if c.is_(cond, on=c.me):
            c.save(on=c.me, against=cond.value)
            return


@power(
    "p15931",
    level=10,
    cls="x7_921",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    trigger="you start your turn dominated, stunned or unconscious",
    on=Trigger(TurnStart, _my_turn, "you start your turn"),
    dropped=("c.effects_on()",),
)
def p15931(c: Cast) -> None:
    """"For the same duration as the triggering condition" needs the
    effect imposing it read back off the creature; save-ends is the
    duration all three of these conditions carry in practice and is what
    both halves are given."""
    if c.dying:
        return
    for cond in (Condition.DOMINATED, Condition.STUNNED, Condition.UNCONSCIOUS):
        if c.is_(cond, on=c.me):
            c.ignore_condition(cond, on=c.me, until=When.SAVE_ENDS)
            c.dazed(on=c.me, until=When.SAVE_ENDS)
            return


@power(
    "p15932",
    level=3,
    cls="x7_921",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.WEAPON],
    dropped=("c.draw()", "c.as_basic(charge=)"),
)
def p15932(c: Cast) -> None:
    """Drawing a weapon first is an equipment operation the engine has no
    verb for, and the printed Special -- this row in place of a melee basic
    attack on a charge -- is a standing substitution `c.as_basic` cannot
    narrow to a charge."""
    c.attack(_best(c), vs=AC)
    if c.landed:
        c.damage(c.w(2), _best_mod(c))


# ==========================================================================
# x7_923 -- a shadow bargainer
# ==========================================================================


def _grant_ca_to_all(c: Cast, until: When) -> None:
    """"You grant combat advantage." `c.grants_advantage` names one
    beneficiary or one side of the board, and the side that wants it here
    is the enemy side, which is not one of its words."""
    for foe in c.enemies():
        c.grants_advantage(on=c.me, to=foe, until=until)


@power(
    "p15935",
    level=0,
    cls="x7_923",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
)
def p15935(c: Cast) -> None:
    """A bet on the first attack roll of the turn. The penalty half also
    pays out when no attack is made at all, so it is hung on the end of the
    turn as well as on a miss."""
    settled: list[int] = []

    def win(ev: Hit) -> None:
        if settled or ev.attacker != c.me:
            return
        settled.append(1)
        c.flat(c.roll("1d8"), on=ev.target)
        c.temp_hp(5, on=c.me)

    def lose(ev: object = None) -> None:
        if settled:
            return
        settled.append(1)
        _grant_ca_to_all(c, When.EONT)
        c.condition(Condition.DEAFENED, on=c.me, until=When.EONT)

    def missed(ev: Miss) -> None:
        if ev.attacker == c.me:
            lose()

    def ended(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            lose()

    c.watch(Hit, win, until=When.EONT)
    c.watch(Miss, missed, until=When.EONT)
    c.watch(TurnEnd, ended, until=When.EONT)


@power(
    "p15936",
    level=2,
    cls="x7_923",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
)
def p15936(c: Cast) -> None:
    c.stance()
    _grant_ca_to_all(c, When.STANCE)
    c.bonus("damage", 4, kind="power", on=c.me, until=When.STANCE)


def _i_killed_something(world: World, me: int, ev: object) -> bool:
    """"You kill a nonminion creature". `c.is_minion` is a `Cast` method and
    a predicate is handed a world and an eid, so the block is read the way
    `Cast._stat_block` reads it."""
    from combat_engine.content.loader import load
    from combat_engine.engine.components import Ident

    actor = getattr(ev, "actor", None)
    if getattr(ev, "source", None) != me or actor is None:
        return False
    ident = world.get(actor, Ident)
    if ident is None or not ident.ref.startswith("m"):
        return True
    try:
        return not load(ident.ref).row.get("minion")
    except Exception:
        return True


@power(
    "p15937",
    level=6,
    cls="x7_923",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.HEALING],
    trigger="you kill a nonminion creature",
    on=Trigger(
        Dropped,
        _i_killed_something,
        "you drop a nonminion enemy",
    ),
    narrative=(
        "skill:arcana", "skill:dungeoneering", "skill:nature", "skill:religion",
    ),
)
def p15937(c: Cast) -> None:
    """The third printed option is a bonus to four knowledge skills held
    until the next extended rest. Nothing in a fight rolls Arcana,
    Dungeoneering, Nature or Religion to recall lore, so the option is
    offered and the other two are the ones with anything to do."""
    picked = c.choose(["surge", "attack"], "which boon")
    if picked == "surge":
        c.spend_surge(on=c.me)
    else:
        c.bonus("attack", 1, kind="power", on=c.me, until=When.ENCOUNTER)


@power(
    "p15938",
    level=10,
    cls="x7_923",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=SHADOW,
    trigger="you make an attack roll and dislike the result",
    on=Trigger(
        AttackRolled,
        by_me,
        "you make an attack roll",
    ),
)
def p15938(c: Cast) -> None:
    """"Must use the second result" is `keep="new"`, not `"best"`."""
    c.flat(c.level, on=c.me)
    if c.target is not None:
        c.flat(c.level, on=c.target)
    c.reroll_attack(keep="new", bonus=2)


# ==========================================================================
# x7_941 -- a martial bodyguard
# ==========================================================================


def _ally_hit_near(world: World, me: int, ev: Hit) -> bool:
    from combat_engine.engine.query import distance_between, team

    who = getattr(ev, "target", None)
    if who is None or who == me or team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 5


@power(
    "p16047",
    level=2,
    cls="x7_941",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an ally within 5 squares of you is hit by an attack",
    on=Trigger(Hit, _ally_hit_near, "an ally within 5 squares is hit"),
)
def p16047(c: Cast) -> None:
    """`ally_within` reads the creature the event is *about*, which on a
    `Hit` is the attacker, so the printed sentence needs its own test."""
    c.shift(_half_speed(c, c.me), who=c.me)


@power(
    "p16048",
    level=6,
    cls="x7_941",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger="a creature hits or misses you with a melee or a ranged attack",
    on=(
        Trigger(Hit, both(targets_me, either(by_melee, by_ranged)), "you are hit"),
        Trigger(Miss, both(targets_me, either(by_melee, by_ranged)), "you are missed"),
    ),
)
def p16048(c: Cast) -> None:
    """Both halves of "hits or misses" are declared; half of it would look
    finished and fire on half the attacks."""
    if c.target is None:
        return
    c.swap(c.target)
    c.redirect(to=c.target)


@power(
    "p16049",
    level=10,
    cls="x7_941",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy attacks you while you are adjacent to another creature",
    on=Trigger(
        AttackDeclared,
        both(targets_me, either(by_melee, by_ranged)),
        "an enemy attacks you",
    ),
    dropped=("c.pass_on(attack=)",),
)
def p16049(c: Cast) -> None:
    """Declared on `AttackDeclared` so the four points are in before the
    roll, which is what an interrupt buys. Handing a miss on to a creature
    you have swapped with is a re-aim of an attack already resolved, and
    `c.redirect` only re-aims one still being declared."""
    if not [who for who in c.within(1, of=c.me) if who != c.me]:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 4, kind="power", on=c.me, until=When.EOT)


@power(
    "p16050",
    level=0,
    cls="x7_941",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
)
def p16050(c: Cast) -> None:
    """One card, two blocks: the ally is shoved into place and then the
    swing goes at whoever is in reach after the shift. Highest ability
    modifier, rolled in the body."""
    if c.target is not None:
        c.push(2, on=c.target)
        c.grants_advantage(on=c.target, to="team", until=When.SONT)
    c.shift(_half_speed(c, c.me), who=c.me)
    foes = c.within(1, of=c.me, side="enemy")
    if not foes:
        return
    foe = c.choose(foes, "the secondary target")
    if foe is None:
        return
    c.attack(_best(c), vs=AC, on=foe)
    if c.landed:
        c.damage(c.w(2), _best_mod(c), on=foe)
        c.grants_advantage(on=foe, to="team", until=When.EONT)


# ==========================================================================
# x7_949 -- an elementalist
# ==========================================================================


@power(
    "p16089",
    level=0,
    cls="x7_949",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL, Keyword.SUMMONING],
    todo=("spec.stat_block()",),
)
def p16089(c: Cast) -> None:
    """`c.summon` wants a ref and the spec prints the summoned creature's
    description in prose with no block and no id of its own."""
    ...


@power(
    "p16090",
    level=2,
    cls="x7_949",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ELEMENTAL],
)
def p16090(c: Cast) -> None:
    kinds = [
        DamageType.ACID,
        DamageType.COLD,
        DamageType.FIRE,
        DamageType.LIGHTNING,
        DamageType.THUNDER,
    ]
    picked = c.choose(kinds, "which damage type") or DamageType.FIRE
    c.resist(5, picked, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:endurance", 5, kind="power", on=c.me, until=When.ENCOUNTER)


@power(
    "p16091",
    level=6,
    cls="x7_949",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.ELEMENTAL],
    out_of_combat=True,
)
def p16091(c: Cast) -> None:
    """An errand-runner that fetches, carries and manipulates over an hour
    and a mile. It has no attack, no defences and leaves before a round
    could be counted."""


@power(
    "p16092",
    level=10,
    cls="x7_949",
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(0, 10),
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL, Keyword.ZONE],
    narrative=("skill:perception",),
)
def p16092(c: Cast) -> None:
    """A single-square trap. The Perception DC is the narrative clause:
    the engine consults Perception, but never to ask whether a creature has
    noticed a zone, so there is nothing for the DC to be rolled against.

    "Each creature adjacent to the zone" takes in the one that stepped in,
    which is adjacent to its own square, and the list is taken before the
    damage so a creature dropping out of it mid-sweep is still caught.
    """
    area = c.area()
    zone = c.zone(area, label=f"{c.ref} trap", until=When.ENCOUNTER)

    def sprung(ev: ZoneEntered) -> None:
        if ev.zone != zone or ev.actor not in c.enemies():
            return
        caught = set(c.in_squares(spread(frozenset(area), 1)))
        c.dispel(zone)
        for who in sorted(caught):
            c.flat(5, on=who)
            c.prone(on=who)

    c.watch(ZoneEntered, sprung, until=When.ENCOUNTER, once=True)


# ==========================================================================
# x7_980 -- a martial charger
# ==========================================================================


@power(
    "p16402",
    level=0,
    cls="x7_980",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you hit a creature with a charge attack",
    on=Trigger(Hit, both(by_me, by_charge), "you hit with a charge"),
)
def p16402(c: Cast) -> None:
    """"On a natural 20" is read off `Hit.critical`. The two part company
    only for a character carrying an extended critical range, which is the
    nearest the event gets to the printed number."""
    who = getattr(c.trigger, "target", None)
    if who is None:
        return
    c.push(1, on=who)
    if getattr(c.trigger, "critical", False):
        c.prone(on=who)


@power(
    "p16403",
    level=2,
    cls="x7_980",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are subjected to a push, a pull or a slide from an attack",
    on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"),
)
def p16403(c: Cast) -> None:
    """The follow-up bonus is gated on the enemies that are adjacent after
    the shift, which is what "if you end the shift adjacent to an enemy"
    names, and on the blow being a melee one."""
    c.cancel()
    c.shift(1, who=c.me)
    foes = c.within(1, of=c.me, side="enemy")
    if foes:
        c.bonus(
            "attack", 2, kind="power", on=c.me, until=When.EONT, once=True,
            when=lambda ctx: ctx.get("target") in foes and not ctx.get("ranged"),
        )


@power(
    "p16404",
    level=6,
    cls="x7_980",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p16404(c: Cast) -> None:
    c.shift(_half_speed(c, c.me), who=c.me)
    c.bonus(AC, 2, kind="power", on=c.me, until=When.EONT)
    c.bonus(REF, 2, kind="power", on=c.me, until=When.EONT)


@power(
    "p16405",
    level=10,
    cls="x7_980",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(2),
    target=Target("other_ally", 99, everyone=True),
    keywords=MARTIAL,
    requires=_bloodied,
    requires_text="you must be bloodied",
)
def p16405(c: Cast) -> None:
    """`c.can_flank` is the exception `query.flankers` reads, which is
    exactly what "is considered to be flanking" asks for."""
    who = c.target
    if who is None:
        return
    c.shift(_half_speed(c, who), who=who)
    c.can_flank(on=who, until=When.SONT)


# ==========================================================================
# x7_990 -- a martial charmer
# ==========================================================================


@power(
    "p16450",
    level=0,
    cls="x7_990",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(CHA, vs=WILL, plus=2),
)
def p16450(c: Cast) -> None:
    """The extra die is untyped and rides only the next attack this turn
    against this creature, so it is a `once=True` bonus gated on the
    target rather than a rider on the row."""
    foe = c.target
    if c.strike() and foe is not None:
        c.grants_advantage(to="team", until=When.EONT)
        c.bonus(
            "damage", 0, dice="1d6", on=c.me, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power(
    "p16451",
    level=2,
    cls="x7_990",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=MARTIAL,
)
def p16451(c: Cast) -> None:
    for what in ("attack", "damage", "save"):
        c.bonus(what, 1, kind="power", until=When.EONT)


@power(
    "p16452",
    level=6,
    cls="x7_990",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    dropped=("c.invisible(sustain=)",),
)
def p16452(c: Cast) -> None:
    """The invisibility and its end on an attack are exact. `c.invisible`
    takes no `sustain=`, so the minor action that would carry it past the
    end of your next turn -- and the clause about moving costing you that
    -- have nowhere to go."""
    held = c.invisible(on=c.me, until=When.EONT)
    c.on_attack(
        lambda ev: c.end_effect(held, on=c.me, why="attacked"),
        by=c.me, once=True, until=When.EONT,
    )


def _i_rolled_initiative(world: World, me: int, ev: InitiativeRolled) -> bool:
    return ev.actor == me


@power(
    "p16453",
    level=10,
    cls="x7_990",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    trigger="you and your enemies roll initiative",
    on=Trigger(InitiativeRolled, _i_rolled_initiative, "you roll initiative"),
)
def p16453(c: Cast) -> None:
    """`c.bonus` cannot say this: an initiative bonus is added before the
    d20 and the row is answering a roll that has happened."""
    c.initiative(-10)


# ==========================================================================
# x7_1003 -- an infernal bargainer
# ==========================================================================


@power(
    "p16582",
    level=0,
    cls="x7_1003",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target("any", 1),
    keywords=ARCANE,
    dropped=("c.reroll_attack(standing=)",),
)
def p16582(c: Cast) -> None:
    """The blood price is exact. "Roll twice and use the higher result on
    one attack roll you make this turn" is `c.reroll_attack(keep="best")`
    held open for an attack that has not been declared, and that method
    only answers a trigger."""
    c.flat(c.level)


@power(
    "p16584",
    level=2,
    cls="x7_1003",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    trigger="you take acid, cold, fire or lightning damage",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
)
def p16584(c: Cast) -> None:
    """Declared on `DamageRolled` rather than `DamageApplied`: only the
    former is a Decision, and only there is the resistance in before the
    blow it is answering is measured."""
    wanted = (
        DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING,
    )
    hurts = [d for d in c.trigger.types() if d in wanted]
    if not hurts:
        return
    picked = c.choose(hurts, "which type to resist") or hurts[0]
    c.resist(5 + c.level // 2, picked, on=c.me, until=When.ENCOUNTER)


@power(
    "p16585",
    level=5,
    cls="x7_1003",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.NECROTIC],
)
def p16585(c: Cast) -> None:
    """"Intelligence or Charisma" is a choice the card gives the caster, so
    the row takes the better of the two rather than hard-coding one."""
    c.attack(max(c.int_, c.cha_), vs=FORT)
    mod = max(c.int_mod, c.cha_mod)
    if c.landed:
        c.damage("2d10", mod, dtype=DamageType.NECROTIC)
        c.dazed(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.NECROTIC)
    else:
        c.half_damage("2d10", mod, dtype=DamageType.NECROTIC)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p16586",
    level=9,
    cls="x7_1003",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    dropped=("c.strip_resistance()",),
)
def p16586(c: Cast) -> None:
    """Both aftereffects are hung on the condition ending, which is the one
    announcement a save makes. Losing all resistance on the first failed
    save is the dropped half -- `escalate` has the hook and nothing takes
    a creature's resistances away."""
    who = c.target
    if who is None:
        return
    held = Condition.PETRIFIED if c.attack(max(c.int_, c.cha_), vs=FORT) and c.landed \
        else Condition.IMMOBILIZED
    c.condition(held, on=who, until=When.SAVE_ENDS)

    def after(ev: ConditionEnded) -> None:
        if ev.target == who and ev.condition is held:
            c.slowed(on=who, until=When.SAVE_ENDS)

    c.watch(ConditionEnded, after, until=When.ENCOUNTER, once=True)


# ==========================================================================
# x7_1015 -- a fiend-caller
# ==========================================================================


def _x1015_zone(world: World, eid: int) -> int | None:
    """The zone `p16649` leaves standing, by the label `c.zone` stamps on it.

    `c.zone` falls back to `label or self.ref`, so the zone is already
    findable without the parent having asked for a name.
    """
    from combat_engine.engine.zones import Zone

    for who, zone in world.each(Zone):
        if zone.owner == eid and zone.label == "p16649":
            return who
    return None


def _x1015_zoned(world: World, eid: int) -> bool:
    """"The p16649 power must be active", as a `requires=` gate."""
    return _x1015_zone(world, eid) is not None


def _x1015_origin(world: World, zone: int) -> Square | None:
    """"The zone's origin square" -- read back off the squares it covers.

    `Zone` records no origin, and the parent's own `c.origin` is gone by the
    time this fires. A close burst 2 from a Medium creature is a 5x5 block
    whose centre is exactly the square it was cast from, so the midpoint of
    the extents is that square and not an approximation of it.
    """
    from combat_engine.engine.zones import Zone

    held = world.get(zone, Zone)
    if held is None or not held.squares:
        return None
    xs = [square[0] for square in held.squares]
    ys = [square[1] for square in held.squares]
    return ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)


def _x1015_foe(world: World, me: int, who: int | None) -> bool:
    from combat_engine.engine.query import team

    return who is not None and who != me and team(world, who) is not team(world, me)


def _x1015_entered(world: World, me: int, ev: Any) -> bool:
    zone = _x1015_zone(world, me)
    return (
        zone is not None
        and getattr(ev, "zone", None) == zone
        and _x1015_foe(world, me, getattr(ev, "actor", None))
    )


def _x1015_starts_there(world: World, me: int, ev: Any) -> bool:
    from combat_engine.engine.query import squares as squares_of
    from combat_engine.engine.zones import Zone

    zone = _x1015_zone(world, me)
    who = getattr(ev, "actor", None)
    if zone is None or getattr(ev, "ghost", False) or not _x1015_foe(world, me, who):
        return False
    held = world.get(zone, Zone)
    return held is not None and bool(squares_of(world, who) & held.squares)


@power(
    "p16649",
    level=0,
    cls="x7_1015",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.ZONE],
)
def p16649(c: Cast) -> None:
    """Only the zone. The secondary block is `p16649b` now.

    It was armed here by hand, twice, while that stanza had no ref of its
    own; declaring it as well would have fired the attack twice for one
    enemy walking in. "Until the effect ends, you can use the secondary
    power" is the grant, and `requires=_x1015_zoned` on the other row is the
    Requirement it prints back.
    """
    area = c.area()
    c.zone(area, until=When.EONT)
    c.grant_row("p16649b", on=c.me, until=When.EONT)


@power(
    "p16649b",
    level=0,
    cls="x7_1015",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    requires=_x1015_zoned,
    requires_text="the p16649 power must be active",
    trigger="an enemy enters the zone or starts its turn there",
    on=(
        Trigger(ZoneEntered, _x1015_entered, "an enemy enters the zone"),
        Trigger(TurnStart, _x1015_starts_there, "an enemy starts its turn in the zone"),
    ),
)
def p16649b(c: Cast) -> None:
    """The stanza `p16649` leaves standing, as an opportunity action.

    **At-will, against the block's own type line.** The extractor copies the
    parent's usage onto a second stanza, so this one reads "Encounter"; the
    parent's Effect says the secondary power can be used *at will* while the
    zone lasts, and that is the sentence that decides a cadence. Declared
    `ENCOUNTER` the zone would punish one creature per fight, which is
    neither reading of the card.

    The target is read off the trigger rather than declared: an opportunity
    action is handed its victim by the thing that set it off, and the reach
    is printed from the caster while the push is measured from the zone.

    No `attack=` -- "highest ability modifier" is rolled in the body for the
    reason the module docstring gives.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    zone = _x1015_zone(c.world, c.me)
    origin = None if zone is None else _x1015_origin(c.world, zone)
    if c.attack(_best(c), vs=WILL, on=foe):
        c.damage(0, _best_mod(c), on=foe)
        if origin is not None:
            c.push(3, on=foe, anchor=origin)


@power(
    "p16650",
    level=2,
    cls="x7_1015",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    todo=("c.reroll_check(standing=)",),
)
def p16650(c: Cast) -> None:
    """A standing offer to buy a triple reroll with a healing surge, on
    every roll for a turn. Every reroll verb in the vocabulary answers one
    trigger and none of them can be left lying in wait."""
    ...


@power(
    "p16652",
    level=6,
    cls="x7_1015",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    requires_text="you must use this power during a rest",
    out_of_combat=True,
)
def p16652(c: Cast) -> None:
    """Three questions put to a fiend during a rest, and a knowledge bonus
    that lasts until the next milestone. The Requirement puts it outside a
    fight by construction."""


@power(
    "p16653",
    level=10,
    cls="x7_1015",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.ZONE],
    dropped=("resolve.ctx(origin=)", "c.zone(cost=)"),
)
def p16653(c: Cast) -> None:
    """The defence bonus is laid whole, which is wider than printed: the card gives
    it only against attacks **originating outside the zone**.

    **Re-aimed off `c.grants_in(when=)`, which arrived and is not the hold.** The
    gate exists and is handed the attack context; what the context does not carry is
    where the attack came *from*. It has `attacker`, so the attacker's current square
    is reachable -- but that is not the same thing: a ranged attack's origin can be
    moved by `c.cast_from`, and a burst's origin is a square rather than a creature.
    Asking the attacker's position would be right most of the time and wrong exactly
    where the card is interesting.

    Four extra squares to enter is not difficult terrain either -- that word is worth
    one square."""
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    for d in (AC, FORT, REF, WILL):
        c.grants_in(zone, d, 4, side="team", kind="power")


# ==========================================================================
# x7_997 -- a martial sailor
# ==========================================================================


@power(
    "p16557",
    level=2,
    cls="x7_997",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=MARTIAL,
    dropped=("c.vehicle_speed()",),
)
def p16557(c: Cast) -> None:
    """One skill for the whole party, so the choice is made once on the
    first target and laid on all of them. The ship's speed is the dropped
    half; nothing carries a vehicle."""
    if not c.first:
        return
    skill = c.choose(sorted(SKILLS), "which skill") or "athletics"
    for who in c.targets:
        c.bonus(f"skill:{skill}", 2, kind="power", on=who, until=When.ENCOUNTER)


def _enemy_closed(world: World, me: int, ev: AdjacencyGained) -> bool:
    from combat_engine.engine.query import team

    if not closed_on_me(world, me, ev):
        return False
    return team(world, ev.mover) is not team(world, me)


@power(
    "p16558",
    level=6,
    cls="x7_997",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy enters a square adjacent to you",
    on=Trigger(AdjacencyGained, _enemy_closed, "an enemy moves adjacent to you"),
)
def p16558(c: Cast) -> None:
    foe = getattr(c.trigger, "mover", None)
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(_half_speed(c, c.me), who=c.me)
    if foe is None:
        return
    landed: list[int] = []

    def stuck(ev: Hit) -> None:
        if landed or ev.attacker != c.me or ev.target != foe:
            return
        landed.append(1)
        c.immobilized(on=foe, until=When.SAVE_ENDS)

    c.watch(Hit, stuck, until=When.EONT)


@power(
    "p16559",
    level=10,
    cls="x7_997",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True),
    keywords=MARTIAL,
)
def p16559(c: Cast) -> None:
    """The slow is the price, so it is offered rather than imposed:
    `c.may` asks the creature whose turn it will spoil."""
    who = c.target
    if who is None or not c.may("be slowed", who=who):
        return
    c.slowed(on=who, until=When.EONT)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", on=who, until=When.EONT)
    c.resist_forced(2, on=who, until=When.EONT)
