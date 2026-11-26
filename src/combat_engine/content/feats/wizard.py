"""Wizard feats.

Almost all of these gate on a *keyword* rather than on a named row,
which is the cheapest gate there is: the attack context carries the
power's ref and `dsl.get` reads its keywords off the header. So
"whenever you use an arcane illusion power" is a one-line lambda where
the same sentence about a class feature would be a marker.

The exception is the two that reach into another row's shape -- growing
a blast, borrowing a weapon as an implement -- and both say so.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Hit,
    Keyword,
    SavingThrow,
    Summoned,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import DamageRolled, PowerResolved
from combat_engine.engine.query import deals_damage

#: The five the card lists. Read here rather than inline so the two rows
#: that want them cannot drift apart.
_ELEMENTAL = (
    Keyword.ACID, Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING,
    Keyword.THUNDER,
)


def _has(ctx: dict, *words: Keyword) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and any(w in p.keywords for w in words)


def _illusion_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.ILLUSION in p.keywords
        and Keyword.ARCANE in p.keywords
    )


@power("f682", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an arcane illusion power",
       on=Trigger(Hit, _illusion_hit, "you hit with an illusion"))
def f682(c: Cast) -> None:
    """Combat advantage against what an illusion hit, for a turn or until
    the target shakes the spell off.

    **Both halves now, and the premise the marker rested on was answered
    one layer over.** The old note said the longer form *"needs a
    duration that ends on a particular effect's save, which `When` has no
    member for"*, and asked for `c.grants_advantage(until_save=)`. A
    `When` member is the wrong shape -- a duration word cannot name *one*
    effect, and that is exactly why `features/controllers.py`'s
    `orb_imposition` ends its own hold off `SavingThrow.against`, which
    carries `str(effect)` and so tells one of this creature's saves from
    another. This is the same three lines against the same two readers:
    `c.world.effects.of(victim)` for the `Effect` handle whose `when is
    When.SAVE_ENDS`, and the throw against it for when it goes.

    **Which effect is settled at `PowerResolved`, not in the `Hit`
    window.** The hit is announced inside `resolve.attack`, so the
    power's own save-ends effect has not been laid yet -- the ordering
    the old note worried about is real and it is not a blocker. The
    snapshot taken here plus the one read when the use finishes is the
    difference, so *"the illusion power has an effect that a save can
    end"* means an effect **this use** laid rather than one the target
    was already carrying. `EffectApplied.save_ends` would answer the
    question for a single effect and carries no `power`, which is why the
    read is taken off the resolution instead.

    **`c.extend_effect` rather than a second `c.grants_advantage`.** The
    printed *"instead"* replaces the clock and nothing else, and laying a
    second relation would hand the character two holds to lose one at a
    time. `When.ENCOUNTER` is the cap being lifted -- not a claim that
    the advantage lasts the fight -- and the `SavingThrow` watch is what
    actually ends it. If the target never saves, the fight is over
    first, which is the printed reading.

    `sorted(..., key=lambda eff: eff.id)` for `orb_imposition`'s reason:
    a set of effects has no order and the lowest id is the first one
    laid, so two save-ends effects from one power pick the same one every
    time rather than whichever the iteration happened to yield.

    **`AT_WILL`, and the marker was hiding that.** `lint.py` checks the
    headers of *finished* rows only, so `usage=ENCOUNTER` beside a
    declared trigger went unreported for as long as the `dropped=` did --
    and on a triggered trait that means once per fight, where this card
    prints no limit at all. Un-marking the row is what named it.
    """
    me = c.me
    victim = c.trigger.target
    cast_ref = c.trigger.power
    advantage = c.grants_advantage(on=victim, until=When.EONT)
    if advantage is None:
        return
    before = {eff.id for eff in c.world.effects.of(victim)}
    settled: list[int] = []

    def finished(ev: PowerResolved) -> None:
        if settled or ev.actor != me or ev.power != cast_ref:
            return
        # **The use this hit belonged to, and only that one.** `once=` on
        # the watch asks whether the handler *did* anything, so a use that
        # laid no save-ends effect would leave it armed -- and an at-will
        # illusion cast again before the end of the turn would then be
        # measured against a stale `before`.
        settled.append(1)
        held = next(
            (
                eff
                for eff in sorted(c.world.effects.of(victim), key=lambda e: e.id)
                if eff.id not in before
                and eff.source == me
                and eff.when is When.SAVE_ENDS
            ),
            None,
        )
        if held is None:
            return
        c.extend_effect(advantage, until=When.ENCOUNTER)
        against = str(held)

        def shook_it_off(throw: SavingThrow) -> None:
            if throw.actor == victim and throw.against == against and throw.saved:
                c.world.effects.end(advantage, "saved")

        c.watch(SavingThrow, shook_it_off, until=When.ENCOUNTER, on=victim,
                label=c.ref)

    c.watch(PowerResolved, finished, until=When.EONT, on=me, once=True,
            label=c.ref)


@power("f1140", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1140(c: Cast) -> None:
    """A feat bonus on every arcane illusion power, attack and damage
    both. The later steps are out of scope."""
    me = c.me
    for what in ("attack", "damage"):
        c.bonus(
            what, 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _has(ctx, Keyword.ILLUSION),
        )


@power("f1132", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1132(c: Cast) -> None:
    """Strength to the damage of five elemental keywords. Gated on the
    *power's* keywords rather than on the damage type, which is what the
    card says -- a fire power that happens to deal untyped damage still
    counts."""
    c.bonus(
        "damage", c.str_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _has(ctx, *_ELEMENTAL),
    )


@power("f677", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f677(c: Cast) -> None:
    """The marker this replaces wanted a list of whose summons are whose,
    kept after the fact. A trait does not need one: `Summoned` names the
    summoner as `actor`, and a watch armed at the start of the fight
    catches each arrival as it happens.

    **The keyword gate is written, and the old note here was false.**
    `Summoned.ref` exists and all three emitters stamp it with the
    summoning row -- so the arcane half is `c.keywords_of` on that ref,
    asked the way every other gate in this file is asked. Read through
    `keywords_of` and not off the header, so a keyword some other feat
    granted this wizard counts.

    The event firing is itself the "summoning" half of "arcane summoning
    power", so `Keyword.SUMMONING` is not also asked: the keyword is
    declared on six rows across the tree and absent from almost every
    wizard row that summons, and requiring it would refuse arrivals the
    card plainly covers.

    No type word is printed in front of the bonus."""
    me = c.me

    def arrived(ev: Summoned) -> None:
        if ev.actor != me:
            return
        p = get(ev.ref)
        if p is None or Keyword.ARCANE not in c.keywords_of(p):
            return
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 1, on=ev.summon, until=When.ENCOUNTER)

    c.watch(Summoned, arrived, on=me, until=When.ENCOUNTER, label=c.ref)


@power("f1123", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1123(c: Cast) -> None:
    """*"When you use an arcane attack power and hit two or more creatures,
    you gain a +2 bonus to that power's damage rolls."* +3 at 11th, +4 at
    21st, read off the level the way every other scaling feat bonus is.

    **Written now, and what unblocked it was the resolution order rather
    than anything about counting.** `Hit` is announced per target and the
    damage for each used to be rolled as it went, so by the time the
    second hit was known the first was already paid -- the bonus could
    only ever reach the targets after the second one. `dsl.use` rolls
    every attack of an area or several-targets line before any of its
    damage now (Camille's ruling, `#1394`), so the whole count is in
    before the first damage roll.

    **`f1138` is the control and needed none of this.** It prints nearly
    this sentence with the bonus on *later* attacks, is written, and
    carries no marker -- so counting hits across a use was never the gap.
    This row differs from it by the words *"that power's"*.

    Gated on the power rather than laid flat, which is those two words:
    `ctx["power"]` on the damage side is `detail or self.ref`, so a row
    passing its own `detail=` string would be missed. None of the arcane
    attack powers does, and the honest caveat is here rather than
    nowhere.

    Ended on that power's `PowerResolved` -- the queue is paid before
    that is announced, so the bonus covers exactly the use that earned
    it and no later one.
    """
    me = c.me
    step = 2 + sum(c.level >= n for n in (11, 21))
    #: Targets hit, per arcane attack power, within the use being
    #: resolved. A closure of this arming, so it cannot outlive the board
    #: -- the fault `c.once_per_board` exists for.
    struck: dict[str, set[int]] = {}
    laid: dict[str, Any] = {}

    def counted(ev: Hit) -> None:
        if ev.attacker != me:
            return
        power = ev.power or ""
        declared = get(power)
        if declared is None or declared.attack is None:
            return
        if Keyword.ARCANE not in (declared.keywords or ()):
            return
        seen = struck.setdefault(power, set())
        seen.add(ev.target)
        if len(seen) < 2 or power in laid:
            return
        held = c.bonus(
            "damage", step, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx, _p=power: ctx.get("power") == _p,
        )
        if held is not None:
            laid[power] = held

    def finished(ev: PowerResolved) -> None:
        if ev.actor != me:
            return
        held = laid.pop(ev.power, None)
        if held is not None:
            c.world.effects.end(held, "the use ended")
        struck.pop(ev.power, None)

    c.watch(Hit, counted, on=me, until=When.ENCOUNTER, label=c.ref)
    c.watch(PowerResolved, finished, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} use ended")


def _widenable(ctx: dict[str, Any]) -> bool:
    """A wizard at-will or encounter attack power that deals damage.

    The three conditions the card names for what it may be used on, read
    off the aimed row rather than off keywords: *"a wizard at-will or
    encounter attack power"* and *"you can't use this feat on a power that
    doesn't roll dice for damage"*.

    `query.deals_damage` is the reader for the last one and is the
    established answer to "does this power normally deal damage" -- it
    reads the body as well as the header, because 3,518 rows declare
    `damage=None` and deal damage through `c.damage`. It is marginally
    wider than the printed *"roll dice"*: a row dealing a flat amount
    passes it. That case prices at zero anyway, since the penalty is per
    die and such a blow announces none.
    """
    row = get(str(ctx.get("power") or ""))
    return (
        row is not None
        and row.cls == "wizard"
        and row.attack is not None
        and row.usage in (AT_WILL, ENCOUNTER)
        and deals_damage(row.ref)
    )


@power("f1134", level=1, cls="", usage=AT_WILL, action=ActionType.FREE,
       reach=PERSONAL, target=SELF)
def f1134(c: Cast) -> None:
    """A wider blast, paid for per die. Re-aimed three times before this.

    The first marker named `c.widen_area()`, which has never existed, while
    `c.widen_areas` does and is exactly the payout -- so the instrument agreed
    with the typo and stayed quiet.

    The second named `c.change_dice()`. That verb exists now and is **not**
    this gap: it swaps which die a row rolls, and the price here is "-2 to
    *each die* of damage rolled", which leaves the dice alone and charges
    against every one of them.

    The third named `c.bonus(per_die=)`, on the reasoning that "a modifier
    is laid against a roll's total, so there is nothing that scales with
    how many dice made it". **That is true of `c.bonus` and false of the
    row**, which is the distinction a marker has to get right. Since #703,
    `resolve.deal_damage` hangs the live `Roll` on `DamageRolled` as
    `ev.roll`, and `amount = max(0, rolled.amount)` reads a listener's
    change back -- so a per-die price is a listener away. Measured on a
    board: a 3d6 blow announced faces `[3, 2, 4]` and a listener taking 2
    off each die repriced the blow. No verb is missing for the price.

    **The missing thing is the moment.** The card is *"before using a
    wizard at-will or encounter attack power, you can choose to"* -- a
    per-use decision taken before the row aims, because the payout
    increases the blast or burst and the area is settled during aiming.
    Nothing a trait can arm runs there:

    * `PowerUsed` carries `targets`, so it is already too late;
    * `Power.effect_before` **is** the right moment -- its own note says
      "everything below settles the target list" -- but it is a header
      field on the power being used, so only that power can fill it;
    * `c.pre_empt` is the class-of-powers door the component file points
      at, and it needs the row to read `instead_of`. This clause is not
      "instead of" anything: it adds a square and charges for it.

    So the gap is a facility for offering a per-use choice before aiming,
    for a class of powers rather than a named one -- the same shape
    `Powers.pre_empts` gives the action menu, at `effect_before`'s moment.

    Writing the wider blast alone would be the payout with no price, which
    is a strictly better card than the one printed. Writing it as a
    standing trait would be worse than that: it would widen every power
    all fight and remove the choice the card is made of.

    #1436 holds the design and the three doors that are not it.

    **The sweep that note asked for found a fourth door, and it is a row
    rather than a facility.** `f714` prints the same shape -- *"Before you
    use an area or close arcane power, you can use a free action to..."* --
    and carries no marker, because it is declared `action=FREE,
    usage=AT_WILL` and the character simply uses it before the power. The
    "before" is the player's ordering, not a hook into aiming. So "nothing
    a trait can arm runs there" was asking the wrong question: nothing
    needs to arm, because the row *is* the free action.

    Swept over every spec table before writing this: one other card phrased
    "before using ... you can choose" (this one), and `f714` on the wider
    "before you use a <class> power". Two rows, one shape, and `f714` had
    already solved it.

    **What makes it faithful rather than a payout with no price is that
    both halves read ONE predicate.** `_widenable` above answers the
    card's three conditions, and it gates the widening *and* the penalty:

    * `c.bonus("blast_size", 1, when=_widenable, once=True)` is the
      payout. `dsl._stretched` reads `"blast_size"` with a context
      carrying `{"power": ref}`, which is what lets the gate name the
      aimed row at all -- `f287`, `f601` and `p5275` take the
      same route, measured rather than recalled -- the first draft of this
      sentence named a ref that does not exist and `refs.py` caught it.
    * a `DamageRolled` watch is the price. `#703` hangs the live `Roll` on
      that event, so `ev.roll.dice` is the faces and
      `resolve.deal_damage` re-reads `rolled.amount` after the emit --
      measured at `resolve.py`'s `amount = max(0, rolled.amount)`. So
      `ev.amount -= 2 * len(dice)` is the printed *"-2 penalty to each
      die"*, and a blow rolling no dice is charged nothing.

    Had either half been written without the other, the card would have
    been strictly better or strictly worse than print, which is what the
    old note correctly refused to do.

    **The price follows the power, not the turn.** The first qualifying
    damage roll fixes which row is being paid for, and later rolls of that
    same row are priced too -- an area power announcing one roll per target
    must be charged on each, which `once=True` on the watch would have
    underpriced. A closure list holds that, which is per-use state on this
    effect rather than a module-level store keyed on the world.

    `usage=AT_WILL` and `action=FREE`, both from `f714`'s reading: the card
    prints no per-encounter limit, so `ENCOUNTER` -- which this row
    carried -- was a silent narrowing."""
    widened = c.bonus("blast_size", 1, on=c.me, until=When.EOT,
                      when=_widenable)

    paid: list[str] = []

    def price(ev: DamageRolled) -> None:
        if getattr(ev, "source", None) != c.me:
            return
        row = get(str(getattr(ev, "detail", "") or ""))
        if row is None or not _widenable({"power": row.ref}):
            return
        if paid and paid[0] != row.ref:
            return
        if not paid:
            paid.append(row.ref)
            # **The choice is spent here, not by a duration.** `c.bonus`
            # refuses `once=` on this key and says why: `"blast_size"` has
            # no spend moment of its own, so a `once=` hold would be eaten
            # by the next *attack roll* instead of by the aiming it paid
            # for. Ending it on the first qualifying damage roll is the
            # honest equivalent -- the area is already settled by then, so
            # the power that was widened keeps its wider area and a second
            # power this turn gets nothing.
            if widened is not None:
                c.end_effect(widened, why=c.ref)
        rolled = getattr(ev, "roll", None)
        dice = list(getattr(rolled, "dice", ()) or ())
        if dice:
            ev.amount -= 2 * len(dice)

    c.watch(DamageRolled, price, until=When.EOT)


@power("f1128", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1128(c: Cast) -> None:
    """A longsword as an implement for this class's powers.

    The waiver answers the half that is checked through `c.wielding` -- a
    row asking whether an implement is in hand. That is narrower than
    `c.as_implement`, which rewrites the weapon's group outright and would
    hand over the proficiency the card withholds.

    **Both of the clauses that were named are written, and one of them
    needed nothing.**

    The enhancement is `enhancement=True`, a second word rather than a
    consequence: an implement's enhancement is read off the implement,
    so a weapon standing in for one lends its own only when the card
    says so. `Gear.lends_enhancement` is where it lives and
    `Cast._enhancement_of` reads it, for an implement power with no
    implement in hand.

    *"You do not gain its proficiency bonus"* holds **by
    construction**, which is why it is not a second mechanism:
    `Cast.attack_with` adds proficiency only for a row carrying
    `Keyword.WEAPON`, and an implement power does not carry it. Measured
    rather than assumed -- the withholding was already true the day the
    marker was written.
    """
    # **Two printed facts, both opted into.** Standing in for an
    # implement is one; *"it adds its enhancement bonus to implement
    # attack and damage rolls"* is the other, and an implement's
    # enhancement is read off the implement rather than off whatever is
    # standing in for it -- so it takes a second word.
    c.counts_as("implement", holding="longsword", enhancement=True)
@power("f276", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f276(c: Cast) -> None:
    """More spells in the spellbook. `Powers.owned` is the book and
    `chargen.spellbook` fills it, so this is a build-time number rather
    than anything that happens in a fight."""
