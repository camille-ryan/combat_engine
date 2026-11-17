"""Battlemind, level 7."""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    EACH_ENEMY,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    Attack,
    AttackDeclared,
    Augment,
    Budget,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Position,
    Powers,
    Trigger,
    TurnStart,
    UpTo,
    When,
    Window,
    both,
    enemy_within,
    hits_me,
    leaves_me_out,
    power,
    targets_my_side,
)

from . import PSIONIC_WEAPON, shift_beside


@power(
    "p11169",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1),
        Augment(2, reach=CloseBurst(1), target=EACH_ENEMY),
    ),
    #: *"When making an opportunity attack, you can use this power in place
    #: of a melee basic attack."* "In place of", so it is the offer and not
    #: the designation -- the row does not become a basic attack.
    #:
    #: **`basic_at=(1,)`, because the Special is Augment 1's entire
    #: content.** The import marks each augment at the *end* of the block
    #: before it, which p11104's own errata settles: it rewrites "the
    #: Augment 1 section" to the Effect printed *after* that marker. So a
    #: Special above the marker is base-card -- p11104 and p12959, both of
    #: which say *unaugmented* or name no form -- and one below it, like
    #: this, is the augment's. The two groups also differ exactly as that
    #: reading predicts: the base-section ones have to say *unaugmented* to
    #: exclude the augments, and these two say nothing because their
    #: section already scopes them.
    #:
    #: So standing in costs a power point, which is why `Augment(1)` is
    #: declared with no overrides: the form has to be payable. It rewrites
    #: no header line, so `actions._aimings` leaves it out of the
    #: ordinary menu -- otherwise it is the base card at the price of a
    #: point. #1298.
    instead_of_basic="opportunity",
    basic_at=(1,),
)
def p11169(c: Cast) -> None:
    """Augment 2 is a close burst against each enemy at 2[W], which is a
    header line, so it is declared as one.

    **The Special is declared now and only one clause is still dropped.**
    Augment 1 is that Special -- the row standing in for an opportunity
    attack -- which is indeed not anything the body does, and the header
    says it: `instead_of_basic="opportunity"` with `basic_at=(1,)`.
    `dsl.Power.basic_for`, which this row named, never existed; what was
    missing was the scope, because the base card gives no such permission
    and an unscoped declaration would hand it over free.

    And "the target cannot gain combat advantage" is printed on every form
    and is laid on every form. That clause named `c.no_advantage(gains=)`,
    and the re-aiming was right: the plain verb stops a creature
    *granting* advantage and what was missing was the attacker's half --
    a creature that cannot gain one however the board looks. `#1299` built
    it, and `on=c.target` is obligatory there rather than defaulted, which
    is the one thing to get wrong here."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2) if c.augment == 2 else c.w(), c.con_mod)
        if victim is not None:
            c.no_advantage(gains=True, on=victim, until=When.EONT)


@power(
    "p11170",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
)
def p11170(c: Cast) -> None:
    """"Hits or misses" is two event classes on one hold, and "the first
    time" is a latch rather than `once=`, which would be spent by the wrong
    half of the pair.

    Augment 1 replaces the rider with the target hitting itself, which is
    `c.as_though_hit_by` -- the printed line is "it hits itself with that
    attack", not "it attacks itself", so nothing is rolled. Augment 2 keeps
    the damage and hands you the target's next melee attack to aim: an
    interrupt on `AttackDeclared`, where `c.redirect` moves it."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    if spent == 1:
        known = c.world.get(victim, Powers)
        if known is not None and known.basic:
            c.as_though_hit_by(known.basic, on=victim, by=victim)
        return
    if spent == 2:

        def steer(ev: AttackDeclared) -> None:
            if ev.attacker != victim:
                return
            pool = [x for x in c.within(1, of=victim) if x != victim]
            aim = c.choose(sorted(pool), "whom it attacks instead") if pool else None
            if aim is not None:
                ev.target = aim

        c.watch(
            AttackDeclared, steer, window=Window.BEFORE, until=When.EONT,
            on=victim, once=True, label=c.ref,
        )
        return
    fired: list[int] = []

    def sting(ev: Hit | Miss) -> None:
        if fired or ev.attacker != victim or ev.target not in c.allies():
            return
        fired.append(1)
        c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=victim, from_attack=False)

    held = c.watch(Hit, sting, until=When.EONT, on=victim)
    held.subs.append(c.world.bus.on(Miss, sting, owner=c.me))


@power(
    "p11171",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=FORT),
)
def p11171(c: Cast) -> None:
    """Augment 1 is an Effect -- a step in after the attack, hit or miss.
    Augment 2 buys a weapon die and drops Wisdom from the damage.

    Both Hit lines stay `c.damage`, including the dice-free one: that is the
    attack's own damage roll, so the weapon's enhancement applies to it just
    as it does to the `1[W]` line beside it. #1225."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        if spent == 2:
            c.damage(c.w(), c.con_mod)
        else:
            c.damage(0, c.con_mod + c.wis_mod)
        c.prone()
    if spent == 1 and victim is not None:
        shift_beside(c, 2, victim)


@power(
    "p12425",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
    trigger="an enemy hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def p12425(c: Cast) -> None:
    """The price -- "you don't get your normal standard action on your turn"
    -- is the budget itself, emptied at the start of that turn: both augments
    buy it back, which is most of what they are for.

    Augment 1 steps into the square the target was pushed out of and leaves
    you with the opening. Augment 2 pushes by Charisma, knocks the target
    down and holds it there until its own turn starts, which is what
    `c.prone(held=)` says."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod, dtype=DamageType.FORCE)
        was = c.world.get(victim, Position).square if victim is not None else None
        c.push(c.cha_mod if spent == 2 else 1)
        if spent == 1 and was is not None:
            c.shift(1, to=was)
            c.grants_advantage(on=victim, until=When.EONT)
        if spent == 2:
            c.prone(held=When.SONT)
    if spent:
        return

    def tax(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.standard = 0

    c.watch(TurnStart, tax, until=When.SONT, once=True)


@power(
    "p13051",
    dropped=("Position.second_square",),
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
)
def p13051(c: Cast) -> None:
    """Standing in two squares at once is dropped -- a creature has one
    `Position` -- and both augments are built on that same double: which
    square you keep when it ends, and putting the second one five squares
    away. With no double to speak of there is nothing for either to say."""
    if c.strike():
        c.damage(c.w())


@power(
    "p13052",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1, reach=Melee(1, grows=2)),
        Augment(2, reach=Melee(1, grows=2)),
    ),
)
def p13052(c: Cast) -> None:
    """Weapon + 1 at the base, weapon + 3 under either augment.

    **Camille's ruling, asked on `#1316` and quoted:**

        "A. Replace "melee weapon + 1" with "melee weapon + 3"."

    This is the only card in the corpus whose range line prints a number at
    the base *and* a different one under its augments, so it is the only
    row that can tell *replace* from *stack* apart -- the three sibling
    rows print theirs once and are the same either way. Replace, so the
    augmented reach is weapon + 3 and not weapon + 4.

    **`grows=2`, which is the arithmetic the ruling comes to and not the
    number the card prints.** The ETL recorded the range line's `+1` in
    `GIVES`, keyed by **ref**, so it is added under every augment as well
    as at the base -- an augment that wanted to *reach* weapon + 3 must
    therefore add 2 more. Writing `grows=3` would be the printed figure and
    would reach weapon + 4, which is the reading Camille ruled against.

    **This row was declared `Melee(4)` for both augments and reached
    weapon + 1 under both**, which is the sixth instance of `#1315`'s bug
    and was not among the five it found. `_reach_of` takes its by-weapon
    branch for a card printing "Melee weapon" -- `(weapon reach) +
    GIVES[ref] + stretch` -- and that branch **never reads `size`**, so a
    replacing size is silently discarded. `dsl.reach_of` cheerfully
    *reports* `Melee 4`, which is what makes it invisible: a probe reading
    the declared range passes, and only walking the distances fails. The
    rule that caught it says exactly that about its own first draft.

    Augment 2's pull, which was the half that could not stand alone, is
    written below.
    """
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage(c.w(), c.con_mod)
        if spent == 2:
            c.pull(4)


@power(
    "p13053",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
)
def p13053(c: Cast) -> None:
    """The rider on the class's own step power is written, and the marker
    named the wrong kind of gap.

    It said `c.grant_action_row()` -- a facility for handing out a *row* as
    an action -- and the clause grants nothing: *"if the target triggers
    your p10439 power before the end of your next turn, you shift 1 extra
    square with that power"* is a **distance** on a row that already
    exists, which is what `c.extend_move` is for. Its own docstring names
    eleven rows printing a sentence of that shape.

    **`p10439` had to be made to read it.** That verb's requirement is
    explicit -- *"a row must read it to be changed, with `squares_for` ...
    an `extend_move` on a row whose body still hard-codes its distance is a
    modifier nothing consults"* -- and `p10439`'s body said `c.shift(1)`.
    It reads `c.squares_for` now, and passes the triggering creature in its
    context so this gate can name one.

    **The gate is the printed "the target", not any marked enemy.**
    `p10439` triggers on *an* adjacent marked enemy shifting, and this row
    marks one creature; an ungated square would pay out for whichever of
    them moved. That is the difference between the card and a stronger
    version of it.

    The two augments are louder versions of the same rider and the row
    declares neither -- the spec's augment text does not say which of them
    carries which distance, so they are not guessed at here.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.mark(until=When.EONT)
        c.extend_move(
            "p10439", 1, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("actor") == victim,
        )


@power(
    "p13054",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
)
def p13054(c: Cast) -> None:
    """`c.swap` is the one method that changes two creatures over, so the
    teleport reads as a swap. Both augments mark the target and reach further
    for the ally -- 3 squares, then 5 -- and neither will trade places with
    the target itself."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    if spent:
        c.mark(until=When.EONT)
    reach = {0: 1, 1: 3, 2: 5}[spent]
    mates = [a for a in c.within(reach, side="ally") if a != c.me]
    pool = mates if spent else [victim, *mates]
    partner = c.choose(pool, "who you change places with") if pool else None
    if partner is not None:
        c.swap(partner)


@power(
    "p2634",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
    trigger="an enemy within 5 squares of you targets an ally with an attack",
    on=Trigger(
        AttackDeclared,
        both(enemy_within(5), targets_my_side, leaves_me_out),
        "an enemy within 5 squares of you targets an ally with an attack",
    ),
)
def p2634(c: Cast) -> None:
    """`c.run_at` is the printed "move your speed to a square adjacent to the
    triggering enemy". The price -- no standard action next turn -- is the
    budget emptied at the start of that turn; Augment 2 buys it back.

    Augment 1 penalises the attack this interrupts: `once=True`, because the
    penalty is spent on the roll it was bought for. Augment 2 takes the blow
    instead, which is `c.redirect` on the event being answered."""
    spent = augment(c)
    foe = c.target
    if foe is None:
        return
    c.run_at(foe)
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
        if spent == 1:
            c.penalty("attack", c.cha_mod, on=foe, until=When.EOT, once=True)
        elif spent == 2:
            c.redirect(to=c.me)
    if spent == 2:
        return

    def tax(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.standard = 0

    c.watch(TurnStart, tax, until=When.SONT, once=True)


@power(
    "p2635",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=[*PSIONIC_WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CON, vs=AC),
)
def p2635(c: Cast) -> None:
    """Augment 1 steps you toward the next target between swings, which is
    why it is on every target but the last. Augment 2 adds the modifier to
    the damage and moves the mark into an Effect, so it lands on a miss
    too."""
    spent = augment(c)
    if c.strike():
        c.damage(c.w(), c.con_mod if spent == 2 else 0)
        if spent != 2:
            c.mark(until=When.EONT)
    if spent == 2:
        c.mark(until=When.EONT)
    if spent == 1 and not c.last:
        nxt = c.targets[c.index + 1]
        shift_beside(c, 1, nxt)
