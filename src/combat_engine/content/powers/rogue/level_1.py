"""Rogue, level 1.

One note applies to several rows. A good half of the rogue's list prints
"Melee or Ranged weapon" over a Requirement of "a crossbow, a light blade,
or a sling", and those are declared `MeleeOrRanged` -- both branches, each
offered as its own option. Dexterity attacks either way, so unlike the
ranger these rows need no second attack line; what differs is the range,
the weapon rolled, and whether firing provokes.

Two rows carry a build rider (a bonus for one of the rogue's two tactics).
Nothing in the model records which build a rogue took, so those rows are the
base line only.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Condition,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    """"A crossbow, a light blade, or a sling" -- the rogue's own three."""
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


#: The four holds `f1300`'s clause on `p704` names together. Written here
#: rather than imported from the feat's own file: under #550 the clause
#: lives in `p704`'s body, so the data it reads lives beside it. The same
#: four are still listed in `feats/general_h.py` for the row's three
#: un-migrated powers, and the duplication is the price of migrating one
#: power at a time -- it goes when `f1300`'s last power moves.
_HELD_FAST = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


@power(
    "p704",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p704(c: Cast) -> None:
    """Four feats print a clause on this row: three of one kind, one of none.

    #550's convention: a feat naming one power has its clause written
    here, gated on `c.feat()`, rather than registering a rider from its
    own body. The feat rows stay declared.

    **The grouping comes from the compendium's bracket, and the first
    version of this docstring got it wrong.** A feat's category is printed
    in brackets after its name -- `[Arena Fighting]`, `[Lesser Style]`,
    `[Greater Style]`, or nothing -- and Camille's rule is **one Arena
    Fighting feat, one Lesser Style feat, and any number of unbracketed
    ones** per use of a power.

    So `f972`, `f3188` and `f3234` are **all** Arena Fighting and are one
    chain. The first version paired `f972` with `f1300` and left the other
    two as plain `if`s, which was wrong in both directions at once: it
    denied a clause the character is entitled to and allowed two it is
    not. I had inferred the families from the books rather than reading
    the bracket.

    `f1300` carries no bracket, so it stacks with whichever arena feat
    paid -- a plain `if`, outside the chain.

    **`c.declare` is called before `c.strike()`, and that is the printed
    rule**: "you must declare which of each type you are using before
    making the attack". So a character holding `f972` and `f3188` who
    declares `f972` and then does not crit gets **nothing** -- the
    declaration is not revisited once the die is read.

    The first version of this body put the applicability in each branch
    and fell through, so that character got the shift instead. More
    generous than the card, and `#554` was open about it until the verb
    landed. Do not move these tests back onto `c.feat`: that asks "is it
    held", which is true of every feat the character owns and cannot say
    which one is being applied.
    """
    arena = c.declare("Arena Fighting", "f972", "f3188", "f3234")
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod)

    # **Each clause wrapped in `c.credit`**, which this chain predated --
    # the first #550 wave landed before Camille's call on the attribution
    # fork, so everything here was credited to this row and
    # `audit._claimed` lost each feat's only evidence. #1089.
    if arena == "f972" and c.crit:
        with c.credit("f972"):
            c.penalty(AC, 2, on=c.target, until=When.EONT)
    elif arena == "f3188":
        with c.credit("f3188"):
            c.ignores_difficult(on=c.me, until=When.EOT)
            c.shift(2 if c.race_of(on=c.me) == "r4" else 1)
    elif arena == "f3234":
        with c.credit("f3234"):
            c.push(1, on=c.target)

    # f1300 carries no bracket, so any number of its kind apply: a plain
    # `c.feat` outside the declaration, stacking with whichever arena feat
    # paid.
    if (c.feat("f1300") and c.con_mod > 0
            and any(c.is_(hold, on=c.target) for hold in _HELD_FAST)):
        with c.credit("f1300"):
            c.flat(c.con_mod, on=c.target)


@power(
    "p970",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p970(c: Cast) -> None:
    """**Three feats' clauses are written in here**, which is #550's
    convention: a feat naming one power has its clause in that power rather
    than registering a rider against it from its own file. `c.credit` is
    Camille's call on the attribution fork, so the modifiers this body lays
    are reported as the feats'.

    **Read off `c.declare` and never off `c.feat`.** All three are
    `[Arena Fighting]`, and one feat of that bracket applies to one use of a
    power -- `c.feat` is true of every feat the character holds and cannot
    say which one is being applied.

    `f977` also prints a clause on this row and is **unwritten**: it turns
    on a racial power changing a hit into a miss, which is its own piece of
    work and not a migration.

    **`f991`'s branch goes before `c.strike()`**, which is the window its
    rider was registered in: `_riders`' `used=` table is a `PowerUsed`
    watcher, and `PowerUsed` is announced above the body. A waiver laid
    after the roll would be too late to have decided anything. The other
    two are crit riders off the `Hit` window and sit after the damage.
    """
    arena = c.declare("Arena Fighting", "f975", "f984", "f991")
    if arena == "f991":
        with c.credit("f991"):
            # "With this exploit, you take no penalty to your attack roll
            # for attacking targets at long range."
            c.ignores_long_range(on=c.me, until=When.EOT)
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod + c.cha_mod)
    foe = c.target
    if foe is None or not c.crit:
        return
    if arena == "f975":
        # "The next ally that hits the target before the end of your next
        # turn deals extra damage equal to your Charisma modifier." One
        # ally's blow and not every one of them, so the watcher carries its
        # own latch; and its own `c.credit`, because the outer block is
        # popped when this body returns and the blow comes later.
        spent: list[bool] = []

        def ally_hit(ev: Hit) -> None:
            if spent or ev.target != foe or ev.attacker not in c.allies():
                return
            spent.append(True)
            with c.credit("f975"):
                c.flat(c.cha_mod, on=foe)

        c.watch(Hit, ally_hit, until=When.EONT, on=c.me,
                label=f"{c.ref} next ally")
    elif arena == "f984":
        with c.credit("f984"):
            # "A penalty to attack rolls equal to one-half your Charisma
            # modifier (minimum 1)."
            c.penalty("attack", max(1, c.cha_mod // 2), on=foe,
                      until=When.EONT)


@power(
    "p653",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p653(c: Cast) -> None:
    """The riposte is armed whether or not the opening attack lands.

    It is not a basic attack -- the printed line names Strength vs. AC
    outright -- so it is rolled longhand. The latch is kept here rather than
    with `once=True`, which would burn the trigger on an attack aimed at
    somebody else.

    **`f981`'s and `f994`'s clauses are written in here** (#550), and both
    are about the *counter* rather than the opening blow -- so they sit
    inside the closure, on the riposte's own hit, which is the one place
    that outcome is in hand.

    **Neither could fire where it was.** `f981` registered its clause in
    `_riders`' `landed=` table, which gates on `ev.granted_by == me and
    ev.actor != me` -- the printed "if **you** hit with the immediate
    interrupt attack this exploit grants" is a swing this character makes,
    so that gate was false every time. `f994` sat in the `Hit` table and
    needed `as_="riposte"` to tell the counter from the standard action;
    here the branch is simply inside the counter and the tag is not the
    discriminator. Reported in the migration rather than fixed in place.

    Both are `[Arena Fighting]`, so one chain, declared before the attack
    as the printed rule requires. `f985` and `f988` also print a clause on
    this row -- both trade the interrupt away rather than adding to it --
    and both are still marked on `c.decline_trigger(ref=)`.
    """
    arena = c.declare("Arena Fighting", "f981", "f994")
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    victim = c.target
    if victim is None:
        return
    spent: list[bool] = []

    def riposte(ev: AttackDeclared) -> None:
        if spent or ev.target != c.me or not c.adjacent(victim):
            return
        spent.append(True)
        # `as_="riposte"` so the counter can be told from the opening blow:
        # both carry this row's `power`, and two feats print a clause about
        # the counter alone.
        if not c.attack(c.str_, AC, on=victim, as_="riposte"):
            return
        c.damage(c.w(1), c.str_mod, on=victim)
        if arena == "f981":
            with c.credit("f981"):
                # Two penalties on two different keys, so neither collapses
                # into the other.
                c.penalty(AC, 2, on=victim, until=When.EONT)
                c.penalty(REF, 2, on=victim, until=When.EONT)
        elif arena == "f994":
            # "A -3 penalty to its attack roll with the triggering attack."
            # `once=True` is what names that one roll: it is the very next
            # one this enemy makes, which is the attack being interrupted.
            with c.credit("f994"):
                c.penalty("attack", 3, on=victim, until=When.EONT, once=True)

    c.on_attack(riposte, by=victim, until=When.SONT, label=f"{c.ref} riposte")


@power(
    "p971",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p971(c: Cast) -> None:
    """The walk is an Effect line, so it happens once and before the roll.

    **Two feats speak to that walk and neither could reach it**, because
    the distance was a literal and the clause read no substitution. Both
    halves are here now and they are different mechanisms, not one:

    * `c.squares_for` is the read half of `c.extend_move`, which is how
      `f980` says "move 3 squares instead of 2". The entries add, so the
      feat lays one square and the printed two stay in this body.
    * `c.instead_of` is the read half of `c.pre_empt`, which is how `f976`
      replaces the walk with a check. The whole clause is substitutable
      rather than just its distance, because that card declines the move
      outright.

    Both feats are `[Arena Fighting]` and so only one may apply to a use.
    Neither is in the `c.declare` chain below, which is sound rather than
    an oversight: both reach the walk from outside through `c.pre_empt`,
    and taking `f976`'s substitution means the walk does not happen, so
    the lengthened distance it would have had is never asked for. The two
    cannot both pay.

    **`f990`'s clause is written in here**, which is #550's convention: a
    feat naming one power has its clause in that power rather than
    registering a rider against it from its own file, with `c.credit`
    naming the feat for what the body does.

    **It is read off `c.declare` and not off `c.feat`**, because `f990` is
    `[Arena Fighting]` too and `c.feat` is true of every feat held.
    `f3196` and `f3230` also name this row and are still riders in their
    own files, so they still stack with whichever branch pays, which the
    printed rule forbids. That is the migration being partway through.

    **The crit gate came with the move, and the rider did not have it.**
    The printed clause is *"if you score a critical hit with this
    exploit"*, and the rider was a bare `c.shift(1)` shared with a second
    power whose card says something else entirely -- so it paid on every
    hit on both rows. `_riders`' default table is a `Hit` watcher and
    `ev.critical` is the crit half of that same window; in a body the
    reader is `c.crit`, which is the shape `p704` already uses for a
    crit-gated arena clause.

    **`c.credit` lays nothing here and is kept anyway.** A shift emits
    `Moved` and no effect, so there is nothing for the block to stamp
    today; it is the convention's wrapper and it is what makes a later
    effect in this clause the feat's rather than this row's.

    **`f973`'s clause is written in here too** and it is about the walk
    rather than the swing: "if you take damage from an opportunity attack
    provoked by the movement this exploit grants, reduce that damage by
    your Constitution modifier". A gated `c.resist` and not an interrupt,
    because the damage context carries `opportunity` -- so the reduction is
    a standing modifier that reads it.

    **And it covers the walk and nothing else**, which the rider could not
    say: out in `exploits._riders` the narrowest window to hand was this
    row's own `PowerResolved`, so the reduction also covered the swing.
    Here the move is a line in the body, so the gate is open across that
    line and shut under it. It joins the same chain, so a character holding
    both `f973` and `f990` pays exactly one of them.
    """
    arena = c.declare("Arena Fighting", "f973", "f990")
    if c.first:
        # **The window is a flag the gate reads, not an effect ended
        # afterwards.** `c.resist(when=)` is a gated modifier, so the hold
        # has nowhere to be cancelled from without naming the `Effect` it
        # returns -- and the clause wants exactly the walk below, which a
        # `When` member cannot say. Cleared under the move, so the
        # reduction is false for every later opportunity attack of the
        # turn.
        walking: list[bool] = []
        if arena == "f973":
            with c.credit("f973"):
                walking.append(True)
                c.resist(
                    c.con_mod, on=c.me, until=When.EOT,
                    when=lambda ctx: bool(walking and ctx.get("opportunity")),
                )
        c.instead_of("move", lambda: c.move(c.squares_for(c.ref, 2)))
        walking.clear()
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        # "If you score a critical hit with this exploit, you can shift 1
        # square after the attack."
        if arena == "f990" and c.crit and c.may("shift after the attack"):
            with c.credit("f990"):
                c.shift(1)


@power(
    "p1385",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1385(c: Cast) -> None:
    # One build adds Strength to the damage roll; no build to read.
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p1482",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1482(c: Cast) -> None:
    """The trade of places is an Effect line: a miss still gets it.

    `c.swap` moves both at once, which is the same end state as the printed
    "the ally slides 1 and you shift 1" and cannot end with the two of them
    stacked.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if c.first:
        beside_me = [a for a in c.within(1, side="ally") if a != c.me]
        if beside_me:
            partner = c.choose(beside_me, "who you trade places with")
            if partner is not None:
                c.swap(partner)


@power(
    "p1483",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=WILL),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1483(c: Cast) -> None:
    # One build lengthens the slide to Charisma; no build to read.
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.slide(1)


@power(
    "p1422",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1422(c: Cast) -> None:
    """"Save ends both" becomes two save-ends effects.

    They are saved against separately here, where the printed row clears both
    on one roll -- the nearest the duration model gets.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.grants_advantage(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.grants_advantage()


@power(
    "p1495",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1495(c: Cast) -> None:
    """The standing arrangement is an Effect line, so a miss leaves it behind.

    Armed after the opening attack, which is why that hit does not pay twice.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.slide(1)
    if victim is None:
        return

    def nudge(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.slide(1, on=victim)

    c.watch(Hit, nudge, until=When.ENCOUNTER, label=f"{c.ref} nudge")
