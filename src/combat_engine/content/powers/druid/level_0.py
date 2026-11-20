"""Druid, level 0: the class features and the sentinel's companion rows.

Two things settle most of this file.

**Species is not knowable.** `c.call_companion` builds a body whose numbers
come off its owner and the spec names no database ref for a wolf, a bear or
a living zephyr, so "your *beast* animal companion" is read as "your animal
companion" -- the precedent `ranger/level_2_b.py` set, and for the same
reason: a question that is always false is what a broken row looks like.

**Cantrips are cantrips.** Four of the rows below produce light, open a
door, smell a corpse or pull a rope out of the ground. Those carry
`out_of_combat=True` rather than an invented combat effect.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Companion,
    Dropped,
    Hit,
    Keyword,
    Melee,
    PowerUsed,
    Ranged,
    Square,
    Summon,
    Trigger,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.query import distance_between
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone

PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]

_COMPANION_HIT = "your animal companion hits an enemy within 5 squares of you"


def _companion_of(world: World, owner: int) -> int | None:
    """`c.companion` without a `Cast`, for a trigger predicate."""
    for eid in world.having(Companion):
        if world.get(eid, Companion).owner == owner:
            return eid
    return None


def _racial_die(c: Cast, swung: str) -> str:
    """What `p6189` pays off a hit made with `swung`.

    `p6189`'s own body is the authority and this is the same test it makes:
    *"which die is rolled turns on the triggering power's keywords"* -- the
    weapon die for a weapon attack, a flat `1d8` otherwise. Restated rather
    than called because that row rolls its die *and* hands the type on to a
    lent clause, and the clause below wants the number only.
    """
    row = get(swung)
    weapon = row is not None and Keyword.WEAPON in row.keywords
    return c.w() if weapon else "1d8"


def _swings_with(c: Cast, who: int) -> str:
    """Which row that creature's basic attack actually is.

    **`c.basic`'s own fallback, and it is not the beast row.** `c.basic`
    reads `Powers.basic` and falls back to `basic.MELEE`, so a companion
    with no `Powers` component at all -- which is what `c.call_companion`
    leaves behind when it has no database ref to build from -- swings
    `mba` and not `bmba`. Measured: the `DamageRolled` for the animal's
    half carries `detail='mba'`. Reading `BEAST` here instead would have
    answered the keyword question about a row that did not swing, and the
    two rows differ in exactly that keyword.
    """
    from combat_engine.engine.basic import MELEE
    from combat_engine.engine.components import Powers

    known = c.world.get(who, Powers)
    return (known.basic if known is not None else MELEE) or MELEE


def _both_hit_for_f3797(c: Cast, beast: int, bitten: int, since: int) -> None:
    """`f3797`'s clause: both halves of `p13506` paid `p6189`'s extra damage.

    *"You can use your `p6189` power after you hit with your `p13506`
    power's attack and your animal companion hits ... If you do, your hit
    and your animal companion's hit both deal the extra damage from your
    `p6189` power."*

    Written here and not on `f3797` because the printed condition is the
    **pairing**: `p13506` makes both swings in one body and both return a
    bool, so this is the one place where "you hit *and* it hit" is a
    question that can be asked. `#550`'s convention.

    **`c.credit` is here and is honestly inert**, which is worth saying
    because the convention's stated reason does not apply. The stamp lands
    on `Effect.credit` inside `Effects.apply`, and `c.damage` lays no
    effect -- `DamageApplied` carries `detail`, which is the row's ref. So
    this block credits nothing today: what keeps `f3797` out of the SILENT
    bucket is its `implemented_in=`, which `audit.py` counts separately,
    and the measured `detail` on the extra blow reads `p13506`. The block
    stays because it is the one door every effect verb reaches and the
    clause may grow one.

    **`p6189` has usually already fired by the time this runs, and that is
    what the `since` mark is for.** It is a free action off a `Hit` by the
    character, so the character's own swing above triggers it and it pays
    its die to that one target -- measured: `PowerUsed(power='p6189',
    trigger=Hit#...)` lands between the strike and the animal's swing, and
    `Powers.times("p6189")` is 1 before this clause is reached. So the
    first draft, which priced the clause with `c.expend_row("p6189")` the
    way `feats/ranger_c.py`'s `f2419` does, was refused **every time** --
    there was no use left to buy, and nothing said so.

    What the card actually adds, once that is known, is the animal's half:
    the character's hit is already paid by `p6189` itself. So:

    * `p6189` fired off this attack -- the common case -- and this clause
      pays the animal's half and nothing else;
    * it did not, because the decider declined or it was spent in an
      earlier round, and the clause buys the use with `c.expend_row` and
      pays **both** halves. That is the printed *"you can use your `p6189`
      power"*, which is the permission the sentence opens with.

    Scanned from `since` rather than asked as `c.expended("p6189")`,
    because the power is once per encounter: "spent" is true all fight
    after the first use and the question here is whether it answered *this
    attack*.

    **The judgement the card forces, and the answer.** *"The extra damage
    from your `p6189` power"* is a die that row picks off the attack that
    triggered it -- the weapon die for a weapon attack, a flat `1d8`
    otherwise -- and the two hits need not be the same kind of attack. So
    the die is asked **per hit**, through `_racial_die`, off the row that
    actually swung: `p13506`'s own header for the character's half and
    `_swings_with` for the animal's. The alternative reading -- one amount
    settled by the character's weapon attack and paid twice -- would hand
    the animal a weapon die off a trigger it need not satisfy, and
    `p6189`'s own test is the thing in the tree that already rules on that.
    """
    if not c.feat("f3797"):
        return
    answered = any(
        isinstance(e, PowerUsed) and e.actor == c.me and e.power == "p6189"
        for e in c.world.bus.log[since:]
    )
    with c.credit("f3797"):
        if not answered:
            if not c.expend_row("p6189"):
                return
            c.damage(_racial_die(c, c.ref), on=c.target)
        c.damage(_racial_die(c, _swings_with(c, beast)), on=bitten)


def _companion_hit_near_me(world: World, me: int, ev: Hit) -> bool:
    beast = _companion_of(world, me)
    if beast is None or ev.attacker != beast:
        return False
    return distance_between(world, me, ev.target) <= 5


def _free_square_beside(c: Cast, thing: int) -> Square | None:
    """An empty square touching `thing`, for a slide that names where to."""
    theirs = squares_of(c.world, thing)
    if not theirs:
        return None
    for sq in sorted(spread(theirs, 1) - theirs):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


@power(
    "p13506",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13506(c: Cast) -> None:
    """The companion's half is an Effect line, so it happens whether or not
    the druid's own swing lands. "Its animal attack" is whatever that
    creature's basic attack is -- `c.basic(who=)` reads `Powers.basic`,
    which is the only place a companion's attack is recorded.

    `_both_hit_for_f3797` is the `#550` clause of the feat that rides on
    this pairing, and it is written here because the pairing is: the card
    needs both swings' outcomes in one place and this body is the only
    place they are both known.
    """
    dice = c.w(3 if c.level >= 27 else 2 if c.level >= 17 else 1)
    # Marked before the swing, because `p6189` answers this hit from
    # outside the body and `_both_hit_for_f3797` has to see that it did.
    since = len(c.world.bus.log)
    struck = c.strike()
    if struck:
        c.damage(dice, c.wis_mod)

    beast = c.companion()
    if beast is None:
        return
    c.move_companion(c.speed_of(beast))
    reachable = c.within(1, of=beast, side="enemy")
    if not reachable:
        return
    bitten = reachable[0]
    if c.basic(who=beast, on=bitten) and struck:
        _both_hit_for_f3797(c, beast, bitten, since)


@power(
    "p13524",
    level=0,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL,
    requires_text="must be used at the end of an extended rest",
    out_of_combat=True,
)
def p13524(c: Cast) -> None:
    """Raising the dead between fights: the target is off the board, and the
    surges the ritual costs cannot be regained until three milestones, which
    is a scale no encounter measures."""
    c.note(f"{c.ref}: the dead are restored, at the cost of four surges")


@power(
    "p13540",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    trigger=_COMPANION_HIT,
    on=Trigger(Hit, _companion_hit_near_me, _COMPANION_HIT),
)
def p13540(c: Cast) -> None:
    """The printed Target is the creature the companion just hit, which the
    targeting layer never chose -- it is read off the event instead."""
    ev = c.trigger
    if ev is not None:
        c.prone(on=ev.target)


@power(
    "p13541",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
)
def p13541(c: Cast) -> None:
    """The companion is not a creature the targeting layer offers -- it takes
    no turn and is on nobody's side -- so it is reached through
    `c.companion()` and the burst is the reach rather than the filter."""
    beast = c.companion()
    if beast is not None and distance_between(c.world, c.me, beast) <= 5:
        c.resist(10, on=beast, until=When.EONT)


@power(
    "p15852",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p15852(c: Cast) -> None:
    """"Difficult terrain for all creatures except you" is the zone plus one
    exemption: `c.zone(difficult=<word>)` labels the going and
    `c.ignores_difficult(<word>)` is the druid stepping over it. A bare
    `difficult=True` would slow the caster too.

    **Dismissing it as a minor action is written now**, and the note saying
    it was dropped reasoned from the wrong verb: `sustain=` is indeed about
    holding a zone *up*, but `c.endable` is the one that takes an effect
    down -- *"let whoever holds this effect end it deliberately, for an
    action"*.

    A zone's hold is `Zone.effect`, and it is the `Effect` itself rather
    than an id to look up -- `Conjuration.effect` is the id, which is what
    `p1195` looks up, and reaching for that shape here raised
    `unhashable type: 'Effect'` on the first run.
    """
    aim = c.origin or c.here
    if aim is None:
        return
    size = 3 if c.level >= 21 else 2 if c.level >= 11 else 1
    laid = c.zone(spread({aim}, size), until=When.ENCOUNTER, difficult=c.ref)
    c.ignores_difficult(c.ref, on=c.me, until=When.ENCOUNTER)
    standing = c.world.get(laid, Zone)
    if standing is not None:
        c.endable(standing.effect, MINOR)


@power(
    "p15853",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.CONJURATION],
)
def p15853(c: Cast) -> None:
    """A conjuration that carries things. It occupies no square against
    anybody -- the printed line never says it blocks -- so `solid` is left
    off, which is the default reading for a conjuration.

    Everything the spirit then *does* is object handling and lamplight, so
    the minor, move and free actions listed are noted rather than modelled.
    """
    c.conjure(at=c.origin, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)


@power(
    "p15854",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15854(c: Cast) -> None:
    """"Nothing you do with this power can deal damage or hinder another
    creature's actions" is the printed Special, and it is also the reason
    this is declared inert rather than written."""
    c.note(f"{c.ref}: brighter light, an unlatched door, a gust, a spark")


@power(
    "p15855",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15855(c: Cast) -> None:
    """Four senses, all of them skill checks. The +5 to Perception and
    Insight is the only number and neither skill is rolled in a fight."""
    c.note(f"{c.ref}: senses disease, plants, poison and the dead nearby")


@power(
    "p15856",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=PRIMAL,
)
def p15856(c: Cast) -> None:
    """"Not created by a power" falls out for free: rough ground made by a
    power lives on its `Zone`, and only the map's own squares are in
    `Grid.difficult`. So clearing those and putting them back when the
    effect ends says the printed line exactly, and a zone laid over the
    same squares is untouched.

    "Composed of grass, underbrush or vines" is not asked -- the grid's
    label for a square is a word the map chose and there is no list of
    which words are plants.
    """
    cleared = {
        sq: kind
        for sq in spread({c.here}, 1)
        if (kind := c.world.grid.difficult.get(sq)) is not None
    }
    if not cleared:
        return
    for sq in cleared:
        del c.world.grid.difficult[sq]
    hold = c.effect(c.ref, until=When.EONT, on=c.me)
    if hold is not None:
        hold.on_end.append(lambda: c.world.grid.difficult.update(cleared))


@power(
    "p15857",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15857(c: Cast) -> None:
    """Fifty feet of rope. The engine has no rope."""
    c.note(f"{c.ref}: a vine that serves as a silk rope")


@power(
    "p15858",
    level=0,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.SUMMONING],
    summon=Summon(),
)
def p15858(c: Cast) -> None:
    """The class printing. `summon_of_your_aspect` holds the body.

    **It used to give up the dismissal and carry no marker for it.** The
    docstring admitted as much, in the phrasing the marker census matches,
    while the header declared no `dropped=` -- so the row reported
    finished, `blocked.py` could not see it, and the one instrument that
    would have is that census. The clause is printed plainly:
    *"Otherwise, it lasts until you dismiss it as a minor action or until
    the end of the encounter."*

    The old sentence is described rather than quoted here, because
    `blocked.py --prose` matches a substring and a note reproducing the
    admission in order to say it is paid reads exactly like one that still
    owes it.

    Nothing had to be built to pay it. `f3648b` -- the feat printing of
    **this same card**, specs byte-identical -- had the dismissal written
    all along, so the fix was to read the sibling rather than to write a
    verb. `#1045` ruling A.
    """
    summon_of_your_aspect(c)


def summon_of_your_aspect(c: Cast) -> None:
    """The summon two refs print identically: `p15858` and `f3648b`.

    Their specs are the same **byte for byte**, which is why this is one
    body with no parameters -- unlike `aura_of_healing`, where three
    printings differed in the allowance. `#1045` ruling A: *"the class
    feature should grant the power and point at it"*.

    The block prints no numbers at all, so the summon takes `Summon`'s
    defaults -- the summoner's defences, a surge's worth of hit points, no
    attack of its own. The actions it can be commanded to take are the ones
    its own entry lists, and there is no entry.

    Two clocks, and the card gives them in one sentence. Dropping below 1
    hit point costs the summoner a surge; otherwise it lasts *"until you
    dismiss it as a minor action or until the end of the encounter"*. So
    the hold is `When.ENCOUNTER` and `c.endable` prices the early exit,
    which is how every other deliberate ending in the tree is written.
    `c.summon_inline` spawns a `Companion`, and `c.dismiss_companion` is
    the verb that takes one away.

    `get(c.ref).summon` and not a captured spec: `c.ref` is the **caller's**
    ref, so each printing reads its own declared `Summon`.

    **Which creature arrives is the aspect's, and the aspects' creatures
    ARE given** -- this note used to say the block "prints no numbers at
    all" and take `Summon`'s defaults for everybody. The two
    `cf:druid-protector-f3` sub-options each print two creatures at 1st
    level, and all four are rows of the compendium's `Associate` table,
    imported with their hit points, defences, speed and size. `c.summon`
    has routed an `x10_` ref to `loader.spawn_associate` since `#459`.

    The pair is **offered** rather than picked, because the card offers
    it: *"you can use this power to summon <one> or <the other>"* is a
    choice made each time the power is used, not at creation. A druid
    holding neither sub-option -- every druid that is not a protector --
    gets the inline summon it got before, which is the printed reading
    for a block that names no creature.

    `c.feat` on the sub-option rather than `c.chosen_option` on the
    parent, for `p13649`'s two reasons: the parent grants the option it
    drew, so the sub-option is in `Powers.known`; and `lint.py` wants an
    `implemented_in=` pointer's target to name the ref in its own
    source, which a dict-driven loop does not.
    """
    pair: tuple[str, ...] = ()
    if c.feat("cf:druid-protector-f3s0"):
        pair = ("x10_40", "x10_42")
    elif c.feat("cf:druid-protector-f3s1"):
        pair = ("x10_47", "x10_48")
    picked = c.choose(list(pair), f"{c.ref}: which creature") if pair else None
    beast = (c.summon(picked, at=c.origin, after=c.me) if picked
             else c.summon_inline(get(c.ref).summon, at=c.origin))
    if not beast:
        return
    c.endable(
        c.effect(f"{c.ref} summoned", until=When.ENCOUNTER, on=c.me),
        MINOR, then=c.dismiss_companion,
    )

    def fell(ev: Dropped) -> None:
        if ev.actor == beast:
            c.spend_surge(on=c.me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power(
    "p16117",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
    trigger=_COMPANION_HIT,
    on=Trigger(Hit, _companion_hit_near_me, _COMPANION_HIT),
)
def p16117(c: Cast) -> None:
    """The second slide names its destination -- "to a square adjacent to the
    zephyr" -- so the square is found first and passed as `to=`; handed to
    the decider a five-square slide would happily go the other way.
    """
    ev = c.trigger
    beast = c.companion()
    if ev is None or beast is None:
        return
    c.slide(3, on=beast)
    landing = _free_square_beside(c, beast)
    if landing is not None:
        c.slide(5, on=ev.target, to=landing)
