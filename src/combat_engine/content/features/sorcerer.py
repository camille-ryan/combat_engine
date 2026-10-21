"""The sorcerer's second feature set, and the two sources that have no leg.

Twenty-five refs were dispatched for this file and fifteen of them are not
declared, because the tree already carries what they say. The report names
each one against the ref that carries it; what follows is what is left.

**The four sources.** `cf:sorcerer-f0s0` .. `f0s3` are the sub-options of
`cf:sorcerer-f0`, which `powers/sorcerer/souls.py` writes: it dispatches on
two of the legs in `chargen.BUILDS["sorcerer"]` and implements both in
full. Those two children say nothing their parent has not already said --
one of them would have laid a second +2 to AC on being bloodied, on top of
the parent's -- so neither is here. Of the other two, the third source has
a leg now and plays with its unsayable clauses named; the first is still
`cf:sorcerer-soul-rest` and still refused, because the phase it cycles on
is clocked on a rest nothing announces.

**The elementalist.** `cf:sorcerer-elementalist-*` is a whole second set of
class features, and `docs/blocked.json` recorded it as unwritable for one
reason: nothing for `c.build` to answer, so every row would arm for every
sorcerer or for none. Four legs are now in `chargen.BUILDS["sorcerer"]`, one
per elemental specialty, each carrying the damage type its specialty is
sworn to -- so `c.element()` answers "your elemental bolt deals X damage"
without a second place to record it. Every row here is gated with
`on_leg(...)`, which is the deal-everything-and-refuse-at-use arrangement
`c.grant_row` documents, rather than handing rows out at arming time.

Its thirteen cards -- the bolt, the eight specialty at-wills and the four
escalations -- are reprints of `p16222` and `p16224`..`p16235`, and the
specialty each pair belongs to is read off the specialty rows rather than
guessed: three of the four name their second option by ref, and the fourth
names both of its own. So the pairs run in the order the specialties are
listed, and `cf:sorcerer-elementalist-f3` uses that order to find the
escalation its leg is owed.

The 15th-, 23rd- and 25th-level lines of the specialties are paragon and
epic; the project stops at 10 and they are not gaps.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    STR,
    WILL,
    ActionType,
    Build,
    Cast,
    DamageType,
    Gear,
    Hit,
    Keyword,
    Miss,
    Mod,
    PowerResolved,
    PowerUsed,
    ShortRested,
    TurnStart,
    When,
    World,
    get,
    power,
    query,
)
from combat_engine.engine.resolve import spent_action_point

#: The armour the resilience clause rules out, in the page's own wording --
#: "not heavy armor" rather than the inverse of the light list.
_HEAVY = ("chain", "scale", "plate")

ARCANE = [Keyword.ARCANE]

#: The key `i2693x1` widens, and the number is **how many d20 faces fire
#: the third source's rider** -- not the floor those faces start at.
#:
#: `c.amount_for` takes the largest entry, and a lower floor is a *wider*
#: window, so written as a floor a card loosening 20 to 16 would lose to the
#: printed 20 every time and read as though it had applied. One face is the
#: card as printed; five is 16 and up. Two items widening it take the wider,
#: which is the rule `amount_for` already holds for every other grant.
#:
#: Spelled as a plain key and not as a `cf:` ref, like
#: `controllers.IMPOSITION_RAISE` beside it: a `cf:` string reads as a
#: declared row, and this is a mechanic inside one.
STORM_FACES = "sorcerer:storm-faces"

#: The four legs, in the order the class page lists the specialties. The
#: order is load-bearing: the specialty rows and the escalations are
#: numbered along it.
SPECIALTIES = ("air", "earth", "fire", "water")

#: The specialty features, one per leg, in the same order.
_SPECIALTY_ROWS = tuple(
    f"cf:sorcerer-elementalist-f2s{n}" for n in range(len(SPECIALTIES))
)

#: The escalation each leg is owed, in the same order. These are the rows
#: `powers/sorcerer/level_0.py` already carries; the class page reprints
#: them inside the feature and the reprints are not declared again.
_ESCALATIONS = ("p16224", "p16225", "p16226", "p16227")

#: The elementalist's at-will, which the specialty riders hang on.
BOLT = "p16222"


def _elementalist(world: World, eid: int) -> bool:
    """Any of the four specialties -- what the shared features ask about."""
    held = world.get(eid, Build)
    return held is not None and bool(held.choices & set(SPECIALTIES))


def _arcane_power(ctx: dict[str, Any]) -> bool:
    """"The damage rolls of arcane powers", as a modifier gate.

    Asked of the row being used rather than laid flat: a sorcerer swinging
    a mace is not casting, and the printed line says arcane.
    """
    declared = get(str(ctx.get("power") or ""))
    return declared is not None and Keyword.ARCANE in declared.keywords


def _on_bolt_hit(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"On a hit" for the elemental bolt.

    Held for the fight, because the enhancement is a standing property of
    the bolt rather than a one-shot.
    """
    me = c.me

    def watcher(ev: Hit) -> None:
        if ev.attacker == me and ev.power == BOLT:
            fn(ev)

    c.watch(Hit, watcher, until=When.ENCOUNTER, on=me, label=f"{c.ref} bolt")


#: The three cosmic phases, in the page's own numbering -- sun, moon, stars.
#: The order is load-bearing: "your phase immediately changes to the next
#: higher-numbered phase (or back to the phase of the sun if you are in the
#: phase of the stars)" is arithmetic on it.
_PHASES = ("sun", "moon", "stars")

#: Resist 5, rising to 10 at 11th and 15 at 21st, which the page states once
#: for all three phases rather than per phase.
def _resistance(level: int) -> int:
    return 15 if level >= 21 else 10 if level >= 11 else 5


def enter_phase(c: Cast, which: str, *, guard: int = 0) -> None:
    """Hold `which` as the phase, replacing whatever was held, and lay it.

    **Module level and not a closure**, because `i961x1` steps this
    sorcerer's phase from another file -- a tattoo whose whole property is
    "when you use your second wind you can change your phase to the next
    higher-numbered phase". A closure inside the feature row could not be
    reached from there.
    """
    from combat_engine.engine.types import DamageType as _DT

    me = c.me
    ward = guard or _resistance(c.level)
    for eff in list(c.world.effects.of(me)):
        if eff.label.startswith("cf:sorcerer-f0s0 phase "):
            c.world.effects.end(eff, "the cycle moved on")
    c.effect(f"cf:sorcerer-f0s0 phase {which}", on=me, until=When.ENCOUNTER)
    shield = {"sun": _DT.COLD, "moon": _DT.PSYCHIC, "stars": _DT.RADIANT}[which]
    c.resist(ward, shield, on=me, until=When.ENCOUNTER)


def step_phase(c: Cast) -> str:
    """Advance to the next higher-numbered phase, wrapping stars to sun.

    Returns the new phase, or "" when this creature is in none -- which is
    every character without the feature, and is why the callers do not have
    to ask whether it has one.
    """
    here = phase_of(c)
    if not here:
        return ""
    nxt = _PHASES[(_PHASES.index(here) + 1) % len(_PHASES)]
    enter_phase(c, nxt)
    return nxt


def phase_of(c: Cast) -> str:
    """Which phase this sorcerer is in, or "" before the first rest.

    Held as a labelled `c.effect` rather than a component: the phase is
    chosen at a rest and changes mid-fight, so it is encounter state, and an
    effect is the thing this engine already suspends, resumes and tears down
    with everything else. `Build.choices` is the wrong home for the same
    reason `c.element` is right to live there and this is not -- an element
    is picked once at build time and never moves.
    """
    for eff in c.world.effects.of(c.me):
        if eff.label.startswith("cf:sorcerer-f0s0 phase "):
            return eff.label.rsplit(" ", 1)[-1]
    return ""


# -- the two sources with no leg -------------------------------------------


@power(
    "cf:sorcerer-f0s0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def sorcerer_f0s0(c: Cast) -> None:
    """The source that cycles through three phases.

    **Written.** `events.ShortRested` landed, which is the moment the phase
    is chosen at, so the state machine has somewhere to live: the phase is
    held as a labelled `c.effect` (see `_phase_of`), the sun burns what
    stands beside it at the start of each turn, the stars step out of the
    way of a miss, and becoming bloodied once advances the cycle -- stars
    wrapping back to sun, which is why `_PHASES` order is load-bearing.

    **The moon's AC is laid now, and `c.bonus(compute=)` was the wrong name
    for the gap.** The clause is "a bonus to AC equal to the number of
    conscious enemies adjacent to you", and the old note said a modifier
    carries the value it was laid with. `Mod.roll` is the half that note
    missed: it is "called once per time the modifier is read, which is once
    per roll", so a crowd that changes between swings is counted at each
    one. `c.bonus` only reaches it through a `dice` string, but a body may
    build its own `Mod` and hand it to `effects.apply(mods=)` -- 103 call
    sites in 65 files here already do -- so no `Cast` door was in the way.
    Untyped, because the card prints no type word in front of "bonus".

    `f2440` still names the symbol and is left alone: its other half is
    `c.mark_penalty()`, so whether the same reasoning frees it is a question
    about that row and not this one.

    The paragraph below is kept because its reasoning about the leg still
    holds and is the reason `chargen.BUILDS` is not on this marker.

    **`chargen.BUILDS` dropped from the marker, because this row's own reasoning
    already rules it out.** The paragraph below says a leg "with only a third of
    the feature behind it would deal a sorcerer two of three phases that never
    arrive" -- so a leg is not wanted *until* the rest announces itself, and
    naming `BUILDS` made the row report ready the moment legs existed. One gap,
    and it is the event.

    `cf:sorcerer-soul-rest` is the reason and it is unchanged by the legs
    added for the elementalist: the phase is chosen at the end of a short or
    an extended rest and steps on whenever the sorcerer is bloodied or
    spends a daily, so the feature is a state machine clocked on a rest
    nothing announces. `turns.short_rest` does exist -- the marker used to
    name `chargen.short_rest()` and went red the moment somebody looked --
    but a rest that emits no event is one no row can run inside, which is
    the same gap five artificer and bard rows name. A leg for it with only
    a third of the feature
    behind it would deal a sorcerer two of three phases that never arrive,
    so the whole row was refused rather than part of it offered. Two thirds
    of it arrive now, and the third is a number that is too small rather
    than absent.
    """
    me = c.me

    # **Chosen at the end of a rest**, which is the moment this row waited on.
    def chosen(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        picked = c.choose(list(_PHASES), "which cosmic phase")
        # `c.choose` answers `None` when there is nobody to ask or the
        # choice is declined, and the page gives no "no phase" state -- the
        # sorcerer is always in one of the three. The sun is where the cycle
        # starts, so that is the answer a silence means.
        enter_phase(c, picked or _PHASES[0])

    c.watch(ShortRested, chosen, until=When.ENCOUNTER, on=me)

    # The phase of the sun burns what stands next to it, at the start of each
    # of this sorcerer's turns.
    def burn(ev: Any) -> None:
        if getattr(ev, "actor", None) != me or phase_of(c) != "sun":
            return
        for foe in c.enemies():
            if c.adjacent_to(me, foe):
                c.flat(c.mod(STR), dtype=DamageType.FIRE,
                       dtypes=(DamageType.FIRE, DamageType.RADIANT), on=foe)

    c.watch(TurnStart, burn, until=When.ENCOUNTER)

    # The phase of the moon is worth whatever the crowd is, so the number is
    # **read** at the roll rather than laid at arming: enemies close in and
    # step away between swings, and `Mod.roll` is consulted once per read.
    def crowd() -> int:
        return sum(
            1
            for foe in c.enemies()
            if query.conscious(c.world, foe) and c.adjacent_to(me, foe)
        )

    c.world.effects.apply(
        me,
        me,
        When.ENCOUNTER,
        label=f"{c.ref} moon AC",
        mods=[
            (
                me,
                Mod(
                    what=AC.value,
                    value=0,
                    kind="untyped",
                    label=c.ref,
                    when=lambda ctx: phase_of(c) == "moon",
                    roll=crowd,
                ),
            )
        ],
    )

    # The phase of the stars steps out of the way of a miss.
    def slip(ev: Any) -> None:
        if getattr(ev, "target", None) != me or phase_of(c) != "stars":
            return
        if getattr(ev, "attacker", 0) in c.enemies():
            c.teleport(c.mod(STR), who=me)

    c.watch(Miss, slip, until=When.ENCOUNTER)

    # **The cycle, which is the half with no moment of its own until now.**
    # "The first time you become bloodied during an encounter" -- once, so
    # the watch ends with its own firing.
    def advance(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        step_phase(c)

    from combat_engine.engine.events import Bloodied

    c.watch(Bloodied, advance, until=When.ENCOUNTER, on=me, once=True)


@power(
    "cf:sorcerer-f0s2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def sorcerer_f0s2(c: Cast) -> None:
    """The third source: a damage modifier and two resistances at once.

    It has a leg now -- `chargen.BUILDS["sorcerer"]` carries one per
    printed source but the first, which is still `cf:sorcerer-soul-rest`
    -- so the two writable clauses arm and the rest is named.

    The damage half is gated on the row being arcane rather than laid
    flat, the way `cf:sorcerer-elementalist-f0` gates its own: a sorcerer
    swinging a mace is not casting. The paragon steps are out of scope.

    "While this resistance is active, your arcane powers ignore all
    targets' resistance to that damage type up to the value of your
    resistance" is one `c.ignore_resistance` per type, capped at the same
    5 and gated on the same arcane test, so the two halves cannot drift
    apart. It is laid on the caster because it is a thing the caster
    does, not a thing done to the creature being hit.

    **The trade is written now.** It is an immediate action printed inside
    a trait, with no card ref of its own to decorate -- which is exactly
    the reaction `c.arm_trigger` exists for: it charges the holder the
    immediate the printed action costs, off the same `Encounter.spend`
    budget a declared trigger pays from, so the trade and any other
    immediate cannot both be taken in one round. Asked in the `when=`
    gate rather than in the body, because the body runs after the budget
    has already been spent.

    Ending the resistance ends the resistance-gated half with it: the
    ignore-resistance clause is printed "while this resistance is
    active", so the four holds go together and the latch stops a second
    hit buying a second bonus for a resistance that is already gone.
    Within one fight it never comes back, the printed return being on a
    rest.

    **The natural-20 rider is written now and `cf:sorcerer-soul-nat20` is
    retired.** Its premise was "a moment nothing announces" -- the rider
    fires *after* the attack's other effects, and `PowerUsed` is announced
    before the body runs. `events.PowerResolved` is that moment and says so
    in its own docstring, and it carries `rolls`, every `AttackResult` the
    use produced in order, so the faces are all readable in one watch
    rather than one per swing. `AttackResult.natural` is the die and
    `AttackResult.target` is who the blow finally landed on, which is the
    creature to push -- not `ev.targets`, since an interrupt may have moved
    the blow onto somebody else.

    **The push is per qualifying roll and the flight is once per use.** The
    card gives one distance and one gust; a two-target power that rolls two
    twenties surges around both enemies and moves the caster once.

    The threshold is read through `c.amount_for` rather than written as 20,
    because `i2693x1` loosens it. See `STORM_FACES` for why the stored
    number is a count of faces and not the floor.
    """
    if not c.build("f0s2"):
        return
    if c.dex_mod > 0:
        c.bonus(
            "damage", c.dex_mod, until=When.ENCOUNTER, on=c.me,
            when=_arcane_power,
        )
    sworn = []
    for kind in (DamageType.THUNDER, DamageType.LIGHTNING):
        sworn.append(c.resist(5, kind, until=When.ENCOUNTER, on=c.me))
        sworn.append(c.ignore_resistance(
            5, kind, until=When.ENCOUNTER, on=c.me, when=_arcane_power
        ))
    spent = [False]

    def trade(_ev: Hit) -> None:
        spent[0] = True
        for hold in sworn:
            c.end_effect(hold, why="traded for the bonus to defences")
        for defended in (AC, FORT, REF, WILL):
            c.bonus(defended, 4, on=c.me, until=When.EONT, kind="power")

    c.arm_trigger(
        Hit, trade,
        when=lambda ev: not spent[0]
        and getattr(ev, "target", None) == c.me
        and c.may(
            "end the resistance for a bonus to all defences", default=False
        ),
        cost=ActionType.IMMEDIATE_INTERRUPT,
        until=When.ENCOUNTER, on=c.me, label=f"{c.ref} trade",
    )

    def surged(ev: PowerResolved) -> None:
        if ev.actor != c.me:
            return
        # `_arcane_power` is the gate the two clauses above use. It takes a
        # modifier context rather than an event, so it is fed the one key it
        # reads -- one reading of "arcane power" for all three halves of
        # this feature, which cannot then drift apart.
        if not _arcane_power({"power": ev.power}):
            return
        # `spent_action_point` is true for the whole turn the point was
        # spent on, which is the reading four other rows already take. It is
        # here rather than in `i2693x1` because the gate is asked where the
        # amount is read.
        faces = max(1, c.amount_for(STORM_FACES, 1, {
            "power": ev.power,
            "action_point": spent_action_point(c.world, c.me),
        }))
        caught = [r for r in ev.rolls
                  if getattr(r, "natural", 0) >= 21 - faces]
        if not caught:
            return
        if not c.may("push the target and ride the wind", who=c.me):
            return
        for roll in caught:
            victim = getattr(roll, "target", 0)
            if victim:
                c.push(1, on=victim)
        far = 1 + c.dex_mod
        if far > 0:
            # A sorcerer has no fly mode of its own, so the mode is lent for
            # the gust and taken back with the turn. `c.move(at=)` measures
            # the mode rather than the ground speed, which is the whole
            # reason the pair is written this way everywhere else.
            c.mode("fly", far, on=c.me, until=When.EOT)
            c.move(far, at="fly", who=c.me)

    c.watch(PowerResolved, surged, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} storm")


# -- the elementalist ------------------------------------------------------


@power(
    "cf:sorcerer-elementalist-f0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f0(c: Cast) -> None:
    """The whole feature is "you gain `p16222`", and the engine has already
    done it.

    `chargen.loadout` deals a character every level-0 row of its class, so a
    sorcerer of any build knows the bolt before this row arms and
    `c.grant_row` correctly returns nothing. The call is still the row: a
    creature assembled by hand rather than by `loadout` -- a monster with a
    named hand, a test board -- has the sentence honoured. What it must not
    become is a `c.forbid` on everything else, which is the shape
    `c.grant_row` warns about.
    """
    c.grant_row(BOLT)


@power(
    "cf:sorcerer-elementalist-f1",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
    dropped=("chargen.power_choice()",),
)
def elementalist_f1(c: Cast) -> None:
    """The damage bonus and the armour clause, both off Constitution.

    The bonus is untyped -- the card prints no word in front of "bonus" --
    and it is the only one of its kind an elementalist has, because
    `cf:sorcerer-f0` returns early on a leg that is neither of its two.

    "Use your Constitution modifier in place of your Dexterity or
    Intelligence modifier to determine your AC": `chargen.defences` has
    already put the better of those two into the number, so what the clause
    is worth is the difference and nothing else.

    The third clause -- an extra at-will of your choice at 9th and 19th --
    is a pick made when the character is built, and no body can make it.
    """
    step = 2 * (c.level >= 5) + 3 * (c.level >= 15) + 3 * (c.level >= 25)
    c.bonus(
        "damage",
        c.con_mod + step,
        until=When.ENCOUNTER,
        on=c.me,
        when=_arcane_power,
    )
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in _HEAVY:
        return
    swap = c.con_mod - max(c.dex_mod, c.int_mod)
    if swap > 0:
        c.bonus(AC, swap, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:sorcerer-elementalist-f2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f2(c: Cast) -> None:
    """"Choose an elemental specialty. You gain the benefits of that
    specialty."

    The choice is the leg, so this row carries what every specialty prints
    the same way and each `-f2sN` carries only what its own choice adds.
    All four print the resistance identically, differing in a damage type
    that the leg already records, so it is laid once here -- written four
    times it would have been four rows that mostly repeated each other.

    The handing-over is a no-op under `chargen.loadout`, which deals every
    level-0 row of the class and leaves each `-f2sN` to refuse itself on the
    three legs it is not for. It is written anyway for the creature that was
    assembled by hand, which would otherwise hold the leg and none of what
    it buys.
    """
    if c.level >= 5:
        kind = c.element()
        if kind is not None:
            c.resist(10, kind, until=When.ENCOUNTER, on=c.me)
    for name, ref in zip(SPECIALTIES, _SPECIALTY_ROWS, strict=True):
        if c.build(name):
            c.grant_row(ref)


@power(
    "cf:sorcerer-elementalist-f2s0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("air"),
    requires_text="needs the air specialty",
)
def elementalist_f2s0(c: Cast) -> None:
    """Which type the bolt deals is on the leg and the resistance is on the
    parent, so this specialty is left holding one clause: "on a hit, its
    target gains vulnerable 3 to **your** elemental attacks until the end of
    your next turn".

    **Written.** The old note said `c.vulnerable` "takes an amount and a
    damage type with nothing on the attacker's side", which predates #471:
    `when=` keeps the entry as a triple on `Defences.vulnerable_when` and
    `resolve.deal_damage` reads it beside resistance, against the same
    damage context. So the scope is a gate on two keys that context already
    carries -- `source` is who is dealing it and `power` is the row that
    rolled it -- and the scope narrows to this sorcerer rather than making
    every other creature's lightning land harder, which was the objection.

    Scoped by **keyword and not by a list of refs**: the card says "your
    elemental attacks", and `Keyword.ELEMENTAL` is what the class's rows
    carry, the bolt included. No type is passed, because the vulnerability
    is to the attacks rather than to a damage type.
    """
    me = c.me

    def mine(ctx: dict[str, Any]) -> bool:
        if ctx.get("source") != me:
            return False
        rolled = get(str(ctx.get("power") or ""))
        return rolled is not None and Keyword.ELEMENTAL in rolled.keywords

    def exposed(ev: Hit) -> None:
        c.vulnerable(3, until=When.EONT, on=ev.target, when=mine)

    _on_bolt_hit(c, exposed)


@power(
    "cf:sorcerer-elementalist-f2s1",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("earth"),
    requires_text="needs the earth specialty",
)
def elementalist_f2s1(c: Cast) -> None:
    """The bolt slows what it hits."""
    _on_bolt_hit(c, lambda ev: c.slowed(until=When.EONT, on=ev.target))


@power(
    "cf:sorcerer-elementalist-f2s2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("fire"),
    requires_text="needs the fire specialty",
)
def elementalist_f2s2(c: Cast) -> None:
    """"Its damage increases by 1d6" is a die added to the bolt's own roll,
    so it is a damage modifier gated on the row rather than a second hit:
    written the other way it would be untyped where the bolt is not, and it
    would take the maximum on a critical instead of a roll."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: ctx.get("power") == BOLT,
    )


@power(
    "cf:sorcerer-elementalist-f2s3",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("water"),
    requires_text="needs the water specialty",
)
def elementalist_f2s3(c: Cast) -> None:
    """"Slide each creature adjacent to its target" -- every creature, not
    every enemy, and not the target itself."""

    def wash(ev: Hit) -> None:
        for who in c.within(1, of=ev.target, side="any"):
            if who != ev.target:
                c.slide(1, on=who)

    _on_bolt_hit(c, wash)


@power(
    "cf:sorcerer-elementalist-f3",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f3(c: Cast) -> None:
    """The escalation the leg is owed, and the ladder of extra uses.

    "An additional use of the power each encounter" has no header field a
    body can reach -- `uses` is data read before the fight -- so it is
    written as a refund: each time the escalation is spent, one of the
    allowance is handed back, up to the number the level has earned. The
    once-per-round limit is printed on the card and stays there, so a
    refunded use cannot be spent again in the same round.

    `PowerUsed` is announced before the body runs, which is usually a trap
    and is not one here: the use has been spent by then, which is exactly
    what this watch is waiting for.
    """
    me = c.me
    mine = ""
    for name, ref in zip(SPECIALTIES, _ESCALATIONS, strict=True):
        if c.build(name):
            mine = ref
    if not mine:
        return
    c.grant_row(mine)
    left = [(c.level >= 3) + (c.level >= 7) + (c.level >= 13)]

    def refund(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == mine and left[0] > 0:
            left[0] -= 1
            c.restore_use(mine, on=me)

    c.watch(PowerUsed, refund, until=When.ENCOUNTER, on=me, label=c.ref)
