"""Monster abilities, level 8: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=REF,
printed=13)` and `Damage("2d8", 5)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the seven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; and a stat block that prints no
range at all means melee 1.

Five things this file had to settle.

**"The m2833 resists damage"** is a trigger with nothing on any event to
read. `DamageApplied.absorbed` is temporary hit points rather than
resistance -- a different question with a plausible-looking answer -- so
what the sentence names is asked of the creature's own `Defences.resist`
against the type that just arrived. Resistance that eats a blow whole still
announces a `DamageApplied` of 0, which is the case the printed line most
obviously means.

**"Fire and radiant damage"** is one roll of two types and a header holds
one. Unlike level 7's "fire *or* radiant", there is no choice to make: the
header keeps the first printed type and a creature resistant only to the
other takes this in full, where the card would let the resistance bite. The
same approximation level 7 accepted for a damage *modifier*, which carries
no type at all.

**"Ranged 10, or 20 underwater"** is two ranges on one line where the second
is not the user's choice but the encounter's, which is exactly what
`requires_alt` gates. The damage half of the same sentence cannot be
declared beside it: `Power.damage_of` exists and nothing in the engine calls
it, so `damage_alt` is a header field that is read by nobody -- see the
report. The header therefore keeps the dry line and the wet one is rolled in
the body, the arrangement level 7 settled on for a printed line with two
expressions in it.

**"A penalty to all defences, and ongoing damage, save ends both"** is one
effect carrying both. `c.penalty` makes an effect per defence and `c.ongoing`
another on top, which is five saving throws where the page prints one --
and a victim that shakes off its Reflex penalty while keeping the rest.
`_all_defences` a level below solved half of this; these two rows print the
burn on the same line, so the burn is carried here too.

**A recharge line that is a sentence rather than a die** -- "when first
bloodied", "when a creature saves against this power", "if the power misses
every target" -- stays a 6+ in the header, because that is what the card
shows and what `actions.recharge` rolls, with the printed sentence armed on
top of it. The last of the three keeps no state between calls, so whether
anything was hit is read off the log from this use's own `PowerUsed`.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_06.brutes import (
    DEFENCES,
    _is_bloodied,
    _same_row,
    _struck_by,
)
from combat_engine.content.monsters.level_07.controllers import _resist
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
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
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Damage,
    DamageType,
    Defences,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    SavingThrow,
    TurnStart,
    Usage,
    When,
    World,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.dsl import Range
from combat_engine.engine.events import (
    DamageApplied,
    Dropped,
    EffectApplied,
    Event,
    LeaveSquare,
    PowerUsed,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, distance_between, squares, team
from combat_engine.engine.triggers import Trigger, about_me, hits_me


def _sapped(
    c: Cast,
    ongoing: int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    defences: tuple = DEFENCES,
    penalty: int = 2,
    on: int | None = None,
) -> Effect | None:
    """"Ongoing N and a penalty to those defences, save ends **both**."

    One effect carrying everything, for the reason `_all_defences` gives a
    level below and one more: applied separately the victim gets a saving
    throw per piece and can shake off half of a thing the card says is one.
    """
    who = c.target if on is None else on
    if who is None:
        return None
    mods = [
        (who, Mod(what=d.value, value=-penalty, kind="untyped", label=c.ref))
        for d in defences
    ]
    return c.world.effects.apply(
        who, c.me, When.SAVE_ENDS, label=c.ref, mods=mods, ongoing=(ongoing, dtype)
    )


def _missed_everybody(c: Cast) -> bool:
    """Did this use of the row land on nobody at all?

    A body is called once per target and keeps nothing between the calls, so
    the answer is read off the log from this use's own `PowerUsed` -- which
    `use` emits before the first target is reached.
    """
    ref, me = c.ref, c.me
    start = 0
    for past in reversed(c.world.bus.log):
        if isinstance(past, PowerUsed) and past.actor == me and past.power == ref:
            start = past.seq
            break
    return not any(
        isinstance(e, Hit) and e.attacker == me and e.power == ref
        for e in c.world.bus.log[start:]
    )


def _underwater(world: World, _eid: int) -> bool:
    """A printed "or 20 underwater", asked of the encounter rather than of
    anybody in it -- which is what `c.terrain` is, from a `requires=` gate
    that gets `(world, eid)` and no `Cast`."""
    return "aquatic" in getattr(world, "terrain", frozenset())


# ==========================================================================
# Artillery
# ==========================================================================


# --------------------------------------------------------------------------
# m215
# --------------------------------------------------------------------------


@power(
    "m215a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m215a0(c: Cast) -> None:
    """No range is printed where the later rows print one, which the levels
    below settled means melee 1."""
    if c.strike():
        c.hit()


@power(
    "m215a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
)
def m215a1(c: Cast) -> None:
    """The rubble is an Effect line, so it is laid whether or not anything
    was hit, and once for the whole burst rather than once per creature
    caught -- which is what `c.first` guards. Never running out of stones is
    a fact about ammunition, and the engine counts none.
    """
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, difficult=True, label=c.ref)
    if c.strike():
        c.hit()


@power(
    "m215a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 6, kind=LIMITED),
)
def m215a2(c: Cast) -> None:
    """Shoved first and then dropped, in the printed order: prone does not
    stop a push, and a creature knocked away and then down is what the
    sentence describes."""
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


# --------------------------------------------------------------------------
# m2833
# --------------------------------------------------------------------------


def _crit_on_me(world: World, me: int, ev: Event) -> bool:
    """"An enemy scores a critical hit against the m2833." `hits_me` is the
    enemy half; the critical is a field on the `Hit` itself."""
    return hits_me(world, me, ev) and bool(getattr(ev, "critical", False))


def _resisted_damage(world: World, me: int, ev: Event) -> bool:
    """"The m2833 resists damage."

    `DamageApplied.absorbed` counts temporary hit points rather than
    resistance, so it answers a different question with a plausible number.
    What the sentence names is the creature's own `Defences.resist` biting
    on the type that just arrived -- including the case where it eats the
    blow whole, which still announces a `DamageApplied` of 0.
    """
    dtype = getattr(ev, "dtype", None)
    if getattr(ev, "target", None) != me or dtype is None:
        return False
    if dtype is DamageType.UNTYPED:
        return False
    shell = world.get(me, Defences)
    return shell is not None and shell.resist.get(dtype, 0) > 0


#: The five the printed line names. Untyped and the other five are not on it.
_M2833_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _elemental_damage(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _M2833_ELEMENTS
    )


@power(
    "m2833a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m2833a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2833a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 9, dtype=DamageType.NECROTIC),
)
def m2833a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


_M2833_CRITTED = "an enemy scores a critical hit against the m2833"


@power(
    "m2833a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    trigger=_M2833_CRITTED,
    on=Trigger(Hit, when=_crit_on_me, text=_M2833_CRITTED),
)
def m2833a2(c: Cast) -> None:
    """"Until the end of its next turn" is the *target's* clock, which is
    `EOTNT`: the burst answers a blow landed on somebody else's turn, and
    the caster's own next turn is the wrong one to measure from."""
    if c.target is not None and c.strike():
        c.hit()
        c.weakened(until=When.EOTNT)


_M2833_SHRUGGED = "the m2833 resists damage"


@power(
    "m2833a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2833_SHRUGGED,
    on=Trigger(DamageApplied, when=_resisted_damage, text=_M2833_SHRUGGED),
)
def m2833a3(c: Cast) -> None:
    """A die of extra damage on everything it lands, for a turn.

    A damage modifier will not carry it: a `Mod` holds a number and the
    printed line adds dice, which is the reason level 4's charge rider hangs
    off the `Hit` instead. The same shape here, on a clock rather than on
    the encounter.

    An at-will trigger fires as often as it is met, and resisting twice in a
    turn refreshes the die rather than adding a second one -- so the old
    watch comes down first. Left alone it stacked, which is the one thing
    the printed line does not say.
    """
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.of(me)):
        if eff.label == ref and not eff.ended:
            c.world.effects.end(eff, "it resisted again")

    def rider(ev: Hit) -> None:
        if ev.attacker == me:
            c.damage("1d8", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.EONT, on=me, label=ref)


_M2833_SCORCHED = "the m2833 takes acid, cold, fire, lightning or thunder damage"


@power(
    "m2833a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2833_SCORCHED,
    on=Trigger(DamageApplied, when=_elemental_damage, text=_M2833_SCORCHED),
)
def m2833a4(c: Cast) -> None:
    """Which type it learns to shrug off is read off the trigger rather than
    chosen: the printed line names "the triggering damage type" and there is
    exactly one."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        _resist(c, dtype, 5, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m2852
# --------------------------------------------------------------------------


@power(
    "m2852a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 3),
)
def m2852a0(c: Cast) -> None:
    """No range printed, which means melee 1."""
    if c.strike():
        c.hit()


@power(
    "m2852a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 6, dtype=DamageType.FORCE),
)
def m2852a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2852a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m2852a2(c: Cast) -> None:
    """The second sentence is a watch hung on the first effect's life.

    "Until the target saves" is a duration no `When` names, so the watch runs
    on the encounter clock and the hold itself takes it down when it ends --
    the arrangement level 7 uses for an invisibility that a roll gives away.
    Standing beside the victim is asked as each turn begins rather than held
    on anybody, because who is standing where changes constantly.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    hold = c.immobilized(until=When.SAVE_ENDS)
    if hold is None:
        return

    def spreads(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == victim or hold.ended:
            return
        if team(c.world, ev.actor) is not team(c.world, victim):
            return
        if adjacent(c.world, ev.actor, victim):
            c.slowed(until=When.SAVE_ENDS, on=ev.actor)

    watch = c.watch(
        TurnStart, spreads, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} spread"
    )
    hold.on_end.append(lambda: c.world.effects.end(watch, "the target saved"))


@power(
    "m2852a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m2852a3(c: Cast) -> None:
    """No attack roll at all -- the whole printed line is the opening it
    makes. "Grants combat advantage" names nobody, so it is `to="allies"`,
    which is this creature and everything on its side."""
    c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m2852a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 5, kind=LIMITED, half_on_miss=True),
)
def m2852a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
        c.prone()
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m2884
# --------------------------------------------------------------------------


@power(
    "m2884a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 9, dtype=DamageType.FORCE),
)
def m2884a0(c: Cast) -> None:
    """No range printed, which means melee 1."""
    if c.strike():
        c.hit()


@power(
    "m2884a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.FORCE),
)
def m2884a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
    else:
        c.slowed(until=When.EONT)


@power(
    "m2884a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(15),
    target=NO_TARGET,
)
def m2884a2(c: Cast) -> None:
    """Three shots through the row that prints them, so their attack and
    damage lines stay in one place and rescale with it.

    The row declares no targets and picks its own: "each against a different
    target" is the set of who has already been shot at, which the dispatcher
    aiming the row once cannot express. `spend=False`, because the standard
    action was paid for here.
    """
    struck: set[int] = set()
    for _ in range(3):
        pool = sorted(
            foe
            for foe in c.enemies()
            if foe not in struck and distance_between(c.world, c.me, foe) <= 15
        )
        if not pool:
            return
        who = c.choose(pool, "m2884a2: the next shot")
        if who is None:
            return
        struck.add(who)
        use(c.world, c.me, "m2884a1", targets=[who], spend=False)


@power(
    "m2884a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ALLY,
    keywords=[Keyword.CLOSE],
)
def m2884a3(c: Cast) -> None:
    """A step and a swing, both the ally's rather than this creature's, which
    is what `c.grant_attack` is for -- `c.strike` always rolls for the
    caster. The step comes first, as printed, so the swing is taken from
    wherever it ends up; whom it swings at is picked from whatever is in
    reach once it has moved.
    """
    mate = c.target
    if mate is None:
        return
    c.shift(2, who=mate)
    reachable = sorted(
        foe for foe in c.enemies() if distance_between(c.world, mate, foe) <= 1
    )
    if reachable:
        c.grant_attack(mate, on=reachable[0])


_M2884_BLED = "the m2884 is first bloodied"


@power(
    "m2884a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2884_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2884_BLED),
)
def m2884a4(c: Cast) -> None:
    """"First bloodied" needs no latch: `Bloodied` is announced once and the
    row is an encounter power.

    "Until it is hit by an attack" is a duration no `When` names, so both
    bonuses run on the encounter clock and one watch takes them down
    together the first time a blow lands -- half of a pair of guards ending
    is not something the printed line ever says.
    """
    me = c.me
    guards = [c.bonus(d, 4, until=When.ENCOUNTER, on=me, kind="power") for d in (AC, REF)]

    def dented(ev: Hit) -> None:
        if ev.target != me:
            return
        for guard in guards:
            if guard is not None and not guard.ended:
                c.world.effects.end(guard, "it was hit")

    c.watch(Hit, dented, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m2975
# --------------------------------------------------------------------------


@power(
    "m2975a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2975a0(c: Cast) -> None:
    """A gated modifier rather than a hold: what shape an attack is cannot be
    known until one is made, and the attack context carries `ranged` for
    exactly this. Four defences, so four modifiers -- nothing here is
    save-ends, so there is no saving throw to keep to one."""
    me = c.me

    def from_afar(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("ranged"))

    for defence in DEFENCES:
        c.bonus(defence, 2, until=When.ENCOUNTER, on=me, when=from_afar)


@power(
    "m2975a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 4, dtype=DamageType.ACID),
)
def m2975a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2975a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m2975a3(c: Cast) -> None:
    """"Recharge if the power misses every target" is the printed sentence on
    top of the die the database files, and it is answered once the last
    target has been resolved. The body keeps nothing between its calls, so
    whether anything landed is read off the log."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
    if c.last and _missed_everybody(c):
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.restore(c.ref)


_M2975_HURT = "the m2975 takes damage from an attack"


def _hurt_by_an_attack(world: World, me: int, ev: Event) -> bool:
    """"The m2975 takes damage from an attack."

    `about_me` reads `ev.actor` and `DamageApplied` names its subject
    `target`, so it would be false here forever. What makes the damage an
    attack's is the row in `detail` carrying an attack line -- ongoing
    damage and a zone's bite carry none.
    """
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    p = get(getattr(ev, "detail", "") or "")
    return p is not None and p.attack is not None


@power(
    "m2975a4",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M2975_HURT,
    on=Trigger(DamageApplied, when=_hurt_by_an_attack, text=_M2975_HURT),
)
def m2975a4(c: Cast) -> None:
    """Unseen by everybody, not by whoever landed the blow: the printed line
    names no one to hide from."""
    c.invisible(until=When.EONT)


# --------------------------------------------------------------------------
# m3085
# --------------------------------------------------------------------------


_M3085_FELLED = "the m3085 bloodies an enemy or drops one to 0 hit points"


def _felled_by_me(world: World, me: int, ev: Event) -> bool:
    """Was that this creature's doing?

    `Bloodied` and `Dropped` name only the creature that fell, so whose blow
    it was lives in the log alone. Sides are compared with `team` rather than
    with `query.enemies`, which filters out the dead -- on a `Dropped` that
    is every time.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return _struck_by(world, ev, who) == me


@power(
    "m3085a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
)
def m3085a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3085a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 9, dtype=DamageType.FIRE),
)
def m3085a1(c: Cast) -> None:
    """"Fire and radiant damage" is one roll of two types and a `Damage`
    holds one, so the header keeps the first printed. Both keywords are
    declared, which is what a row reading "when hit by a radiant power"
    looks at; a creature resistant only to radiant takes this in full, which
    the card would not let it."""
    if c.strike():
        c.hit()


@power(
    "m3085a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Range("close_blast", 3, alt=Range("area_burst", 3, within=10)),
    target=EACH_CREATURE,
    keywords=[Keyword.CLOSE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 9, kind=LIMITED),
)
def m3085a2(c: Cast) -> None:
    """Two shapes on one printed line, which is what a range's `alt` is:
    each is offered as its own option rather than decided at declaration.

    "Recharge when first bloodied" is the printed sentence on top of the die
    the database files, armed from the body because the row has to have been
    spent before there is anything to give back.
    """
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.prone()
        c.push(2)


@power(
    "m3085a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 4),
    requires=_is_bloodied,
    requires_text="the m3085 must be bloodied",
)
def m3085a3(c: Cast) -> None:
    """The temporary hit points are an Effect line and the row targets
    enemies, so the allies are gathered from the squares rather than from
    the target list, and once for the whole burst. `side="ally"` counts the
    caster among them and "each ally" does not, which is the reading the
    levels below settled on."""
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.temp_hp(5, on=mate)
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3085a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3085_FELLED,
    on=(
        Trigger(Bloodied, when=_felled_by_me, text=_M3085_FELLED),
        Trigger(Dropped, when=_felled_by_me, text=_M3085_FELLED),
    ),
)
def m3085a4(c: Cast) -> None:
    """Both halves of the printed "or" are declared: half of it looks
    finished and would miss every enemy that went from bloodied to nothing
    in one blow."""
    c.temp_hp(c.roll("1d6") + 3, on=c.me)


# --------------------------------------------------------------------------
# m398
# --------------------------------------------------------------------------


@power(
    "m398a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m398a0(c: Cast) -> None:
    """Breathing underwater is what the block's swim speed already means and
    carries no mechanic of its own; the bonus is the half that fights.

    A gated modifier rather than a hold: whether the fight is aquatic is a
    property of the encounter and whom it is swinging at changes shot to
    shot. The attack context carries `target`, which is what "against
    nonaquatic creatures" is asked of.
    """
    me = c.me

    def out_of_its_element(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            who is not None
            and c.terrain("aquatic")
            and not c.is_kind("aquatic", on=who)
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=out_of_its_element)


@power(
    "m398a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m398a1(c: Cast) -> None:
    """Both contexts carry `target`, which is the only key either sentence
    needs -- the damage context carries no `attacker` and no `ranged`, and a
    gate on a key that is not there is silently false rather than an
    error."""
    me = c.me

    def on_the_wounded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(on=who)

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=on_the_wounded)
    c.bonus("damage", 2, until=When.ENCOUNTER, on=me, when=on_the_wounded)


@power(
    "m398a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5),
)
def m398a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m398a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5),
)
def m398a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m398a4",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Range("ranged", 10, alt=Range("ranged", 20)),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    attack_alt=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 7),
    requires_alt=_underwater,
)
def m398a4(c: Cast) -> None:
    """Two ranges on one line where the second is the encounter's business
    rather than the user's, which is what `requires_alt` gates -- branch 0
    has no Requirement, so the dry shot is always open.

    The damage half of the same sentence cannot be declared beside it:
    `Power.damage_of` exists and nothing in the engine calls it, so
    `damage_alt` would be a header field read by nobody (see the report).
    The header keeps the printed dry line, which is what rescales, and the
    wet one is rolled here -- level 7's arrangement for a printed line
    holding two expressions.
    """
    if not c.strike():
        return
    if c.terrain("aquatic"):
        c.damage("3d8", 7)
    else:
        c.hit()


@power(
    "m398a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("4d6", 5, kind=LIMITED, half_on_miss=True),
)
def m398a5(c: Cast) -> None:
    """"Save ends both" on the hit and "save ends" on the miss are each one
    effect, and both carry the row's ref as their label -- which is what the
    recharge sentence then matches on, because `SavingThrow.against` is the
    effect rendered as a string.
    """
    _recharge_on(c, SavingThrow, lambda ev: ev.saved and c.ref in ev.against)
    if c.strike():
        c.hit()
        _sapped(c, 5)
    else:
        c.hit(half=True)
        _sapped(c, 5, defences=())


# --------------------------------------------------------------------------
# m4716
# --------------------------------------------------------------------------


@power(
    "m4716a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.MELEE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 9, dtype=DamageType.ACID),
)
def m4716a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4716a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d10", 3, dtype=DamageType.ACID),
)
def m4716a1(c: Cast) -> None:
    """The splash is a flat number rather than the header's line, and it is
    not an attack: everyone beside the victim simply takes it."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    for who in c.within(1, of=victim, side="enemy"):
        if who != victim:
            c.flat(3, dtype=DamageType.ACID, on=who)


@power(
    "m4716a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 10, dtype=DamageType.ACID, kind=LIMITED),
)
def m4716a2(c: Cast) -> None:
    """One defence rather than four, and the burn on the same effect: "save
    ends both" is one saving throw."""
    if c.strike():
        c.hit()
        _sapped(c, 5, DamageType.ACID, defences=(AC,))


# --------------------------------------------------------------------------
# m655
# --------------------------------------------------------------------------


#: The hold that switches the regeneration off. Both printed sentences are
#: one row, but the healing half reads it a turn later, so it is a named
#: effect rather than a closure variable.
_M655_DOUSED = "m655a0 doused"


@power(
    "m655a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m655a0(c: Cast) -> None:
    """Regeneration, written out: the engine holds no such thing.

    "Has at least 1 hit point" is the printed way of saying it does not knit
    itself back together once it is down, which is `hp > 0` and not
    `alive`. The switch is `c.effect` -- a named hold with no mechanical
    content of its own -- on the source's own clock, so a radiant blow taken
    now is still switching it off when its next turn begins.
    """
    me = c.me

    def regenerate(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is None or health.hp <= 0:
            return
        if any(eff.label == _M655_DOUSED for eff in c.world.effects.of(me)):
            return
        c.heal(5, on=me)

    def douse(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT and ev.amount > 0:
            c.effect(_M655_DOUSED, until=When.EONT, on=me)

    c.watch(TurnStart, regenerate, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(DamageApplied, douse, until=When.ENCOUNTER, on=me, label=f"{c.ref} doused")


@power(
    "m655a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m655a1(c: Cast) -> None:
    """Light and its absence: the engine holds no illumination and darkness
    is not a condition here, so there is nothing for this to change.
    Declared inert rather than given an invented mechanic."""
    c.note("m655a1: bright light to 5 squares, dimmable to 2 as a free action")


@power(
    "m655a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 1, dtype=DamageType.FIRE),
)
def m655a2(c: Cast) -> None:
    """Melee 0 as printed: it has to be in the square, which for a Tiny
    creature is where it already flies."""
    if c.strike():
        c.hit()


@power(
    "m655a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 6, dtype=DamageType.FIRE),
)
def m655a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m655a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.AREA],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 8, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m655a4(c: Cast) -> None:
    """Who is left out is one decision for the whole burst, not one per
    creature caught, so it is made on the first target and the shots are all
    taken there -- the arrangement level 7 settled on for a row whose
    printed line chooses once. Two is the printed ceiling, and offering
    fewer is the point of `optional`.

    The pool is its allies and not itself: "creatures in the burst" catches
    the caster where the origin is close enough, and the printed exception
    is for two *allies*, so a burst dropped on its own head burns it.
    """
    if not c.first:
        return
    caught = [t for t in c.targets if t is not None]
    mine = set(c.allies())
    spared: set[int] = set()
    for _ in range(2):
        pool = sorted(w for w in caught if w in mine and w not in spared)
        if not pool:
            break
        who = c.choose(pool, "m655a4: an ally left out of the burst", optional=True)
        if who is None:
            break
        spared.add(who)
    for who in caught:
        if who in spared:
            continue
        if c.strike(on=who):
            c.hit(on=who)
        else:
            c.hit(on=who, half=True)


@power(
    "m655a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def m655a5(c: Cast) -> None:
    """A conjuration rather than a zone: the hand stands in a square and
    nothing walks through it, which is the clause a zone cannot say.

    "Or until it uses this power again" is one live hand, so an older one is
    dismissed before the new one is made -- ending the effect that holds it
    is what takes it off the board. `speed=5` is the printed Move Action.
    Picking things up is not a combat operation and the engine weighs
    nothing, so the other two sub-actions have no mechanics to write.
    """
    for eff in list(c.world.effects.live.values()):
        if eff.label == c.ref and not eff.ended:
            c.world.effects.end(eff, "it conjured another")
    room = sorted(
        sq
        for sq in spread({c.here}, 5)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not room:
        return
    spot = c.choose(room, "m655a5: where the hand appears")
    if spot is not None:
        c.conjure(spot, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m275
# --------------------------------------------------------------------------


@power(
    "m275a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=6, kind=MINION),
)
def m275a0(c: Cast) -> None:
    """No range printed, which means melee 1."""
    if c.strike():
        c.hit()


_M275_CAUGHT = "the m275 suffers an effect that a save can end"


def _save_ends_on_me(world: World, me: int, ev: Event) -> bool:
    """`EffectApplied` rather than `ConditionApplied`: the printed line says
    "an effect a save can end", and an effect carrying nothing but ongoing
    damage announces no condition at all. Its subject is named `target`, so
    `about_me` would be false forever here."""
    return getattr(ev, "target", None) == me and bool(getattr(ev, "save_ends", False))


@power(
    "m275a1",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M275_CAUGHT,
    on=Trigger(EffectApplied, when=_save_ends_on_me, text=_M275_CAUGHT),
)
def m275a1(c: Cast) -> None:
    """"Against the triggering effect" is what `against=` picks: without it
    `c.save` takes whichever save-ends hold it finds first, which on a
    creature already burning is the wrong one. The label is read off the
    trigger rather than guessed."""
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


@power(
    "m275a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m275a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: braver shoulder to
    shoulder.

    Who is standing beside it changes every time anybody moves, so this is a
    gated modifier asked as the defence is looked up rather than a bonus put
    on and taken off. The gate ignores the context entirely -- it is about
    the board, not about the attack -- and "another of these" is an `Ident`
    match, because `c.is_kind` answers about type words several stat blocks
    share.
    """
    me = c.me

    def shoulder_to_shoulder(_ctx: dict[str, Any]) -> bool:
        return any(
            a != me and _same_row(c, a, "m275") and adjacent(c.world, a, me)
            for a in c.allies()
        )

    c.bonus(AC, 2, until=When.ENCOUNTER, on=me, when=shoulder_to_shoulder)


# --------------------------------------------------------------------------
# m4884
# --------------------------------------------------------------------------


@power(
    "m4884a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4884a0(c: Cast) -> None:
    """`LeaveSquare` rather than `AdjacencyLost`: adjacency is diffed once
    the mover has arrived, so by then it has left several squares and only
    the last one is reported. This is announced per square vacated, which is
    what "whenever an enemy leaves a square adjacent to it" counts.

    The ring is recomputed each time rather than captured, because this
    creature flies and does not stay where the trait was armed.
    """
    me = c.me

    def toll(ev: LeaveSquare) -> None:
        if ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.square in spread(squares(c.world, me), 1):
            c.flat(4, on=ev.actor)

    c.watch(LeaveSquare, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4884a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4884a1(c: Cast) -> None:
    """A skill bonus against a passive check and nothing else, which is
    narrative rather than a failure to write: the engine rolls no Stealth
    and holds no passive Perception."""
    c.note("m4884a1: +10 to Stealth against an enemy's passive Perception")


@power(
    "m4884a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage(bonus=8, kind=MINION),
)
def m4884a2(c: Cast) -> None:
    if c.strike():
        c.hit()
