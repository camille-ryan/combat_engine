"""Warlock: the sub-options printed inside the class features.

`cf:warlock-f0` through `cf:warlock-f4` are in `features/strikers.py`, and
nothing here is a feature of its own: each row hangs off one of those.

**The pact, as a choice.** `cf:warlock-f1` is one feature with seven legs
printed under it, and each leg is a `-f1sN` ref. A leg names an at-will
the character simply *knows* and a boon that pays when a cursed enemy
falls. Only the first half is written here: the boons are already paid,
two of them by `cf:warlock-f1`'s own watch and two by rows of their own
(`p4311`, `p16254`), so arming any of them again would pay the printed
sentence twice. Granting the at-will is the half nothing else says --
`chargen.loadout` samples at-wills, so a warlock built here usually does
not have the one its leg says it always has. `cf:warlock-f0` grants its
card for that same reason.

**A boon can be traded away.** Four cards say "instead of your normal pact
boon" and name no pact, so each payout offers itself as the clause `BOON`
and the trading row registers against every ref in `BOONS` -- the shape
`f3232` already had against this leg's narrower `BOON_REGAIN`. The two
payouts in this file offer it; the two outside it do not yet, and `BOONS`
says which. #641.

All seven legs have an entry in `chargen.BUILDS["warlock"]` now and gate
on it with `c.build`. Three of them were written behind a gate no leg
answered and marked `todo=("chargen.BUILDS",)`; the legs landed, so the
marker came off and the bodies were already right.

**Ten of the refs in this batch are not here.** The importer mints a ref
for every card printed on the class page, and most of those cards already
have a compendium entry that is written -- a pact's at-will is printed in
both places, and so is the curse. Declaring the second printing would put
the same card in the menu twice. The skipped refs and the rows that
already carry them are in the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.content.features.strikers import (
    PRIME_SHOT_BONUS,
    extra_damage,
    nearest_to_target,
)
from combat_engine.engine import (
    AT_WILL,
    CON,
    DEFENCES,
    ENCOUNTER,
    FREE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackRolled,
    Cast,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Ranged,
    SavingThrow,
    SkillCheck,
    Trigger,
    When,
    cursed_by_me,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The row that lays the curse, and the label its extra damage is filed
#: under. A curse from anywhere else has to use the same one.
CURSE = "cf:warlock-f4"

#: The sorcerer-king boon's charge. A `c.spend_charge` key, **not** the
#: leg's own encounter use, and the distinction is #529: a trait is
#: `action=NONE` with no trigger, so `turns.arm_traits` spends its single
#: use at arming, before round 1. This row was written against that use and
#: the charge was gone before `p12887` could ever reach it -- driven, 0 -> 1
#: across `arm_traits` for all seven legs, with `c.expend_row` then False.
#:
#: Named here because three files spend or restore it and a second spelling
#: of the key would be two resources that look like one.
FELL = "cf:warlock-f1s4:boon"

#: The clause name `cf:warlock-f1s4` offers its regain under, so a feat can
#: replace it. `f3232` is the one that does -- it takes a power point
#: instead of the charge coming back.
BOON_REGAIN = "boon_regain"

#: The clause name every leg offers its **whole** payout under, for a card
#: that trades the boon away and names no pact -- `f3444` is the one that
#: does. `BOON_REGAIN` above is narrower: one leg's half of the payout,
#: which is why both are offered and this one is offered outermost.
BOON = "boon"

#: Every ref a pact boon is paid at. A row trading the boon away registers
#: against each of them, because the card names no pact and cannot know
#: which leg the character took -- `c.pre_empt`'s own instruction, and a
#: registration against a row the character does not have never fires.
#:
#: **Four of the five offer `BOON` now.** The two that did not are the two
#: outside this file, and both were opened together: `cf:warlock-f1`, whose
#: three legs pay inline in `features/strikers.py`, and `p16254` in
#: `powers/warlock/pacts.py`. They took opposite readers and the reason is
#: the one `instead_of_now`'s docstring draws -- `cf:warlock-f1` pays inside
#: a watcher it installed itself, so `Cast.variant` is 0 for ever and only
#: `instead_of_now` can ask; `p16254` carries a declared trigger, so
#: `Triggers._ask` has already offered the substitution and plain
#: `instead_of` reads it.
#:
#: `cf:warlock-f1c12` **used to be the one left**, on the ground that it
#: "pays nothing at all until `c.active_vestige()` lands -- so there is no
#: payout to trade". That has landed: `cf:warlock-f1s6` offers the two
#: primary remnants and bargains with one, and the boon now pays whichever
#: clause the active remnant names. So it has a payout to trade like the
#: rest. Listing it here always cost nothing anyway: a registration against
#: a leg the character does not stand on never fires. #641, #1034.
BOONS = (
    "cf:warlock-f1",
    "cf:warlock-f1s4",
    "cf:warlock-f1c10",
    "cf:warlock-f1c12",
    "p16254",
)

_A_CURSED_ENEMY_FALLS = "an enemy under your curse drops to 0 hit points"


# -- the pacts ----------------------------------------------------------


@power(
    "cf:warlock-f1s0",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("dark"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s0(c: Cast) -> None:
    """This leg's boon is spent through a row, so the row is granted along
    with the at-will. Raising the tally it spends is `cf:warlock-f1`'s, and
    is not armed again here."""
    if not c.build("dark"):
        return
    c.grant_row("p3403")
    c.grant_row("p4311")


@power(
    "cf:warlock-f1s1",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    dropped=("c.deals(may=)",),
    requires=on_leg("elemental"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s1(c: Cast) -> None:
    """The affinity itself is `Build.element`, rolled once at chargen rather
    than after each rest -- nothing on a character survives a rest to be
    re-rolled -- and `c.element` reads the one the leg carries. This leg's
    boon is a row too, so it is granted rather than armed.

    The dropped clause is the substitution: on your own turn an arcane
    power's force, necrotic, poison or psychic damage may be dealt as the
    affinity's type instead. `c.deals` changes every type a creature deals
    rather than four named ones on one named row, so taking it would
    recolour the whole character.

    **Re-pointed twice, and the second time most of it landed.** The first
    re-point was off `c.deals(ref=)`: this card names no row, it names "an
    arcane attack power", a *class*. What it wanted instead was a narrowing
    by **keyword** and a narrowing on **four source types**, since the
    affinity "replaces each instance of force, necrotic, poison, and
    psychic damage" -- and without the second it would recolour every type
    the character deals, which is the widening the paragraph above
    describes.

    **Both of those are parameters now** (#711): `through=Keyword.ARCANE`
    and `from_` taking the set. What is left is the printed **may**. The
    affinity replaces each instance *at the character's option*, and a
    standing retype has no moment to ask -- it is a label read inside
    `Cast._typed`, not a body that runs per blow. The nearest writable
    shape is a choice made once as the turn starts, laid `until=When.EOT`
    off a `TurnStart` watch, which is a narrowing of the card rather than
    the card; that is worth doing and is not this symbol.

    "On your own turn" is **not** part of the gap: that same `TurnStart`
    watch scopes it, the way `f3225` brackets a hold around one power.

    The symbol is `c.deals(may=)` and not `c.deals(optional=)` or a bare
    `may`, for the reason the last one was chosen this way: `blocked.py`
    resolves a parameter name it can see on the signature as **existing**
    and does not read the value word, so a spelling already present would
    have reported this row READY on a facility nobody had built. Checked
    with `blocked._exists` before choosing, the same way
    `warlock.boon_instead_of()` was.
    """
    if not c.build("elemental"):
        return
    c.grant_row("p16256")
    c.grant_row("p16254")


@power(
    "cf:warlock-f1s2",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("fey"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s2(c: Cast) -> None:
    """The at-will is granted; this leg's boon is one of the two
    `cf:warlock-f1` pays off its own watch, so nothing is armed here."""
    if not c.build("fey"):
        return
    c.grant_row("p1456")


@power(
    "cf:warlock-f1s3",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("infernal"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s3(c: Cast) -> None:
    """As the leg above: the at-will is granted and the boon stays with
    `cf:warlock-f1`."""
    if not c.build("infernal"):
        return
    c.grant_row("p1458")


@power(
    "cf:warlock-f1s4",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("sorcerer-king"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s4(c: Cast) -> None:
    """The at-will, and the pact boon that enhances a power.

    **The charge is its own state, and the first version of this row was
    wrong about that.** It read "the boon is a row with `usage=ENCOUNTER`,
    so its charge *is* a use of this feature" -- and a trait's single use is
    spent by `turns.arm_traits` at the start of the fight, so the charge was
    gone before `p12887` could reach it. Driven: `Powers.used` goes 0 -> 1
    across `arm_traits` for all seven legs, and `c.expend_row` then returns
    False every time. `c.times` does not exist either; that note named a
    verb that was never in the surface. #529.

    So the charge is `FELL`, a `c.spend_charge` key. Arming is free,
    spending is explicit, and both rests clear it -- which is what "you
    start each encounter with your boon unspent" needs.

    "When a creature affected by your cf:warlock-f4 drops to 0 hit points,
    your pact boon triggers" -- the regain is watched here rather than
    declared, because this row is also the thing that grants the at-will
    and a row holds a trigger **or** standing work, not both.
    """
    if not c.build("sorcerer-king"):
        return
    c.grant_row("p12887")

    def fell(ev: Any) -> None:
        if cursed_by_me(c.world, c.me, ev):
            # **Offered as a named clause, because a feat replaces it.**
            # `f3232` trades this regain for a power point, and "instead"
            # cannot be said from outside a row that does not offer the
            # clause. `instead_of_now` rather than `instead_of`: this fires
            # inside a watcher this row installed, so there was never a
            # menu entry and `c.variant` is 0 for ever -- the case that
            # verb's own docstring describes.
            #
            # `BOON` wraps `BOON_REGAIN` rather than replacing it. A card
            # saying "instead of your normal pact boon" names no pact and
            # registers against every leg, where `f3232` replaces this
            # leg's regain in particular -- two different trades, so two
            # clauses. Outermost, because taking the whole boon away leaves
            # no regain for the narrower clause to stand in for.
            c.instead_of_now(
                BOON,
                lambda: c.instead_of_now(
                    BOON_REGAIN, lambda: c.restore_charge(FELL)
                ),
            )

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} regain")


@power(
    "cf:warlock-f1s5",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("star"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s5(c: Cast) -> None:
    """Both halves are rows and both are written -- the at-will has a
    compendium entry and the boon is below -- and the leg that says which
    warlock has them now exists."""
    if not c.build("star"):
        return
    c.grant_row("p1457")
    c.grant_row("cf:warlock-f1c10")


#: The two remnants the boon card names as **primary**, as its own clause
#: refs. `cf:warlock-f1c12`'s spec labels one boon clause with each, so this
#: is the printed list rather than a reading of it -- and refs, not names, so
#: `leaks.py` stays honest. Other remnants arrive from daily attack powers,
#: which the card says plainly ("other pact boons are described in the daily
#: attack powers that give you access to new vestiges") and which is why
#: `c.offer_vestige` takes `primary=` rather than owning the whole set.
_PRIMARY_REMNANTS = ("cf:warlock-f1c12s0", "cf:warlock-f1c12s1")


@power(
    "cf:warlock-f1s6",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    requires=on_leg("vestige"),
    requires_text="needs the pact that prints it",
)
def warlock_f1s6(c: Cast) -> None:
    """The leg, and the remnant it bargains with this fight.

    Printed: *"you can choose from between two or more vestige pacts to fuel
    your arcane power"*, and *"you have a pact boon associated with your
    active vestige"*. So a warlock on this pact always has one active, and
    which one is a per-fight choice -- which is exactly `c.bargain`'s
    shape and why it is state rather than a `Build` token.

    **The two primary remnants are the boon card's own clause refs.**
    `cf:warlock-f1c12`'s spec reads *"The pact boons associated with the
    primary vestiges are given below"* and then labels one clause with each,
    so `_PRIMARY_REMNANTS` is not a choice I made -- it is the card's own
    list, and `c.vestiges(primary=True)` hands it to any row that needs the
    subset.

    `c.bargain` does the choosing: it offers a `c.choose` over more than
    one, ends any standing bargain first, and is idempotent on re-arming.
    `usage=ENCOUNTER` is what re-establishes it each fight.

    **Was `dropped=("c.active_vestige()",)`**, and the clause it was missing
    is this one. The verb it named existed; what did not was anybody
    *offering* a remnant for it to be active among, so `c.active_vestige()`
    answered `""` for every reader. #1034 is where that was measured across
    the three rows waiting on it.
    """
    if not c.build("vestige"):
        return
    c.grant_row("cf:warlock-f1c11")
    c.grant_row("cf:warlock-f1c12")
    c.offer_vestige(*_PRIMARY_REMNANTS, primary=True)
    c.bargain(*c.vestiges(primary=True))


# -- the cards only a pact above prints ---------------------------------


@power(
    "cf:warlock-f1c10",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger=_A_CURSED_ENEMY_FALLS,
    on=Trigger(Dropped, cursed_by_me, _A_CURSED_ENEMY_FALLS),
    requires=on_leg("star"),
    requires_text="needs the pact that prints it",
)
def warlock_f1c10(c: Cast) -> None:
    """A bonus to one roll, kept until the end of your turn or until spent.

    The printed Prerequisite is the pact, and it is a leg now, so it is
    asked in the header like the other boons'.

    **All four rolls are written.** The old note said a modifier is laid
    against one named roll, which left the saving throw, the skill check
    and the ability check out -- but every one of those has a wide key that
    is already read: `durations` reads `"save"`, `skills.modifier` reads
    `"skill"` beside the narrow `skill:<name>`, and `skills.ability_check`
    reads `"ability_check"`.

    What `once=` cannot do is spend one bonus across four keys -- its
    branches are attack, damage and defence, and a check is none of them --
    so the latch is hand-rolled over the three events that announce a d20
    this creature rolled. Each drop lays its own untyped set, so three
    drops are the printed +3 on one roll rather than three separate +1s,
    and the first roll ends every set at once.

    The whole payout is offered under `BOON`, for a card that trades the
    boon away without naming a pact. **Plain `c.instead_of` here and not
    `instead_of_now`**: this row carries a declared trigger, so
    `Triggers._ask` has already offered each registered substitution as a
    way of taking the trigger and `c.variant` names the one chosen -- the
    distinction `instead_of_now`'s own docstring draws with `rt:r24-t0`."""
    me = c.me
    # **Read, not hard-coded, so an item can add to it.** `i2343p2` prints
    # "add the enhancement bonus of this rod to the bonus your pact gives
    # you", and there was no bonus to add to: the number lived inside this
    # body, which is the `change_amount` family's whole argument. One line,
    # and the row that wanted it had been marked for it in as many words --
    # "the one content line that would close this is in that file and not in
    # this one". #551's recorded verdict.
    #
    # The default stays the printed 1, so a warlock with no such item is
    # unchanged, and `amount_for` takes the largest rather than summing --
    # two items raising one boon is not two raises.
    def payout() -> None:
        boon = c.amount_for("cf:warlock-f1c10", 1)
        laid = [
            c.bonus(what, boon, until=When.EONT, on=me)
            for what in ("attack", "save", "skill", "ability_check")
        ]

        def spend(ev: Any) -> None:
            who = getattr(ev, "attacker", None)
            if who is None:
                who = getattr(ev, "actor", None)
            if who != me:
                return
            for eff in laid:
                c.end_effect(eff, on=me, why="used")

        for event in (AttackRolled, SavingThrow, SkillCheck):
            c.watch(event, spend, until=When.EONT, on=me)

    c.instead_of(BOON, payout)


def _vestige_augment(c: Cast, victim: int) -> None:
    """The extra effect `cf:warlock-f1c11` gains from the active remnant.

    The card prints one Augment line per primary remnant and a third line
    sending the reader elsewhere for the rest:

        cf:warlock-f1c12s0  one ally who hits the target before the end of
                            your next turn can roll a saving throw
        cf:warlock-f1c12s1  you gain your cf:warlock-f2 bonus against the
                            target until the end of your next turn
        other vestige       see the entry on the daily power that granted
                            access to the vestige

    **Which clause belongs to which remnant is read off the source, not
    guessed, and three things agree.** The leg's own spec names its two
    primary remnants in order; `cf:warlock-f1c12` labels its two boon
    clauses in that same order, which is where `_PRIMARY_REMNANTS` comes
    from; and the *subject* matches independently -- the first clause of
    each pair is about an ally and the second of each is about
    `cf:warlock-f2`. Order alone would have been one coincidence away from
    wrong.

    **On a hit, which the leg states and this card does not.** The at-will
    prints its Augment lines with no `Hit:` prefix, so they read as
    standing effects; the pact says *"you gain an additional effect,
    referred to as an augment, associated with your active vestige **when
    you make a successful attack with this power**"*. That settles it, and
    it is why this is called from inside the hit branch rather than at the
    top of the body.

    **The second clause carries no gate, where `cf:warlock-f1c12`'s does,
    and the difference is the printed verb.** The boon says the bonus
    *"increases to +3"* -- an operation on a standing bonus, so it keeps
    `cf:warlock-f2`'s own "no ally nearer" condition. This one says you
    *gain* that bonus against the target: a grant, scoped to one creature,
    and conditioning it would make the augment worth nothing to a warlock
    who already has the feature it names. The amount is
    `PRIME_SHOT_BONUS` rather than a literal, so the two cannot drift.

    **The third line is not written and wants no symbol.** It defers to the
    granting power's own entry, and the only such power in the imported
    tier is `f2035`, which is still marked -- so the clause has nothing to
    defer to yet rather than a mechanism missing. `#1034` carries it.
    """
    active = c.active_vestige()
    if active == _PRIMARY_REMNANTS[0]:
        mine = set(c.allies())

        def granted(ev: Any) -> None:
            # "One ally **who hits the target**": the ally is identified by
            # the blow, not chosen, so there is nothing to `c.choose`.
            if ev.target != victim or ev.attacker not in mine:
                return
            c.save(on=ev.attacker)

        # `once=True` is the printed "one ally", and it is measured by
        # whether the handler *did* something -- so an ally hitting
        # somebody else, or one with nothing to shake off, does not spend
        # it on a creature the clause never helped.
        c.watch(Hit, granted, until=When.EONT, on=c.me, once=True,
                label=c.ref)
    elif active == _PRIMARY_REMNANTS[1]:
        c.bonus("attack", PRIME_SHOT_BONUS, on=c.me, until=When.EONT,
                kind="untyped",
                # Scoped to this creature and to ranged attacks, which is
                # what "your cf:warlock-f2 bonus against the target" says:
                # that feature's bonus is a ranged one.
                when=lambda ctx: (ctx.get("target") == victim
                                  and bool(ctx.get("ranged"))))


@power(
    "cf:warlock-f1c11",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
    dropped=("c.curse_damage()",),
)
def warlock_f1c11(c: Cast) -> None:
    """The one at-will that moves the curse around: it lands on the target
    or on somebody standing near it.

    "Within the target's line of sight" is the target's question and
    `c.can_see` asks the caster's, so distance is what is checked. Placing
    the curse has to lay its extra damage too -- `c.curse` only sets the
    state -- so the rider `cf:warlock-f4` arms is armed here under the same
    label, which is what a curse from any second source needs.

    **The remnant's augment is written** -- `_vestige_augment` above, which
    carries the reading of which clause belongs to which remnant and why it
    lands on a hit. One clause is still dropped: a creature already cursed
    takes the curse's extra damage *instead of* the target, which wants
    that damage payable on demand rather than on the next hit.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d6", c.con_mod, dtype=DamageType.PSYCHIC)
    # **Before the curse-placement block, which can return early.** The
    # augment is owed to a successful attack, and a hit that finds nobody
    # left to curse is still a successful attack.
    _vestige_augment(c, victim)
    near = [victim, *(e for e in c.within(3, of=victim, side="enemy") if e != victim)]
    pool = sorted(e for e in near if not c.cursed(on=e))
    pick = c.choose(pool, f"{c.ref}: who the curse settles on") if pool else None
    if pick is None:
        return
    c.curse(on=pick)
    extra_damage(c, "1d6", applies=lambda t: t == pick, label=CURSE)


@power(
    "cf:warlock-f1c12",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    requires=on_leg("vestige"),
    requires_text="needs the pact that prints it",
)
def warlock_f1c12(c: Cast) -> None:
    """One boon per remnant, and which one pays is whichever is active.

    The card prints both clauses and labels each with its remnant:

        cf:warlock-f1c12s0  one ally adjacent to you gains a +2 bonus to
                            all defenses until the end of your next turn
        cf:warlock-f1c12s1  the bonus to attack rolls from your
                            cf:warlock-f2 increases to +3 until the end of
                            your next turn

    **A row that paid both would be twice the card**, which is why this
    waited: both halves were sayable on their own and nothing said which
    fires. `c.active_vestige()` is that, now that `cf:warlock-f1s6` offers
    the two and bargains with one.

    **All four defences, not AC.** The card says *"all defenses"*, and
    `Cast.second_wind` records what that costs when only AC is laid: every
    creature two points easier to hit on the other three.

    **`+2` on top of `cf:warlock-f2`'s `+1`, with that row's own gate.**
    The printed line is *"increases to +3"* -- a replacement -- and this
    adds 2 to a standing 1, which is the same number by a different route.
    The route matters because the gate has to match: `cf:warlock-f2` only
    pays when no ally stands nearer the target, so a flat +2 would pay in
    cases the thing it is raising does not. `nearest_to_target` is
    `prime_shot`'s own predicate, shared rather than copied so the two
    cannot drift.

    Where the two readings would differ is if something *else* also moved
    `cf:warlock-f2`'s bonus -- then "+2 more" and "becomes 3" part company.
    Nothing in the tree does today; said here rather than silently assumed.

    The ally is `c.choose`n, because *"one ally adjacent to you"* is a
    choice and the first adjacent body is not an answer to it.
    """
    def pay() -> None:
        active = c.active_vestige()
        if active == _PRIMARY_REMNANTS[0]:
            mates = [a for a in c.within(1, side="ally") if a != c.me]
            if not mates:
                return
            mate = mates[0] if len(mates) == 1 else c.choose(
                mates, "which adjacent ally gains the defences")
            if mate is None:
                return
            for defence in DEFENCES:
                c.bonus(defence, 2, on=mate, until=When.EONT, kind="untyped")
        elif active == _PRIMARY_REMNANTS[1]:
            c.bonus("attack", 2, on=c.me, until=When.EONT, kind="untyped",
                    when=nearest_to_target(c))

    # **Offered as the named `BOON` clause, so a card saying "instead of
    # gaining your normal pact boon" can replace it.** That is `#641`, and
    # the note above `BOONS` records why this row was the one left out: it
    # paid nothing, so there was no payout to trade. It pays now.
    #
    # **`instead_of_now`, and the first draft got this wrong.** I reasoned
    # that a standard action with a menu entry means `Triggers._ask` has
    # already offered the substitution, so plain `instead_of` would read it.
    # The note above `BOONS` says the distinction is a **declared trigger**,
    # not a menu entry: `p16254` carries one, so `_ask` runs and
    # `instead_of` works; `cf:warlock-f1` pays inside a watcher it installed
    # and needs `_now`. This row has no `on=` at all, so `Cast.variant` is 0
    # for ever and it is the second case.
    #
    # Caught by the assertion that the clause is tradeable, which failed on
    # both halves -- the trade did not take and the payout still paid. A
    # wrap nothing tries to replace looks identical either way.
    c.instead_of_now(BOON, pay)
