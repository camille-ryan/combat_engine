"""Five diseases at levels 8 and 10, one row each. #948.

Every body here obeys the package rule: `turns.arm_afflictions` calls the
row at the start of **every** fight off the stage the `Sheet` carried in, so
a stage paragraph lays a **standing** effect and never charges a one-time
cost. An `until=When.ENCOUNTER` hold is re-laid next fight and stops being
laid the moment the disease is cured, which is exactly the printed "while
affected by stage N".

**The stages are not cumulative unless the page says so.** Four of these
five restate the earlier stage's penalties in each later paragraph, or
replace them outright, so the branches are written as the page prints them
-- `== 2` where stage 3 says something else, `>= 2` where stage 3 says
"suffers the effects of stage 2". Reading them all as cumulative would
quietly double x5_93's and x5_27's Will penalty onto a stage that drops it.

**"The target loses a healing surge" is a standing reduction**, written as
`diseases.lost_surges` rather than as `c.spend_surge` -- which is right for
a monster's attack and wrong here, because it takes a fresh surge every
encounter. It does **not** apply to x5_62's aura, where the loss is a
per-turn consequence of standing somewhere and is supposed to repeat.
"""

from __future__ import annotations

from combat_engine.content.diseases import lost_surges
from combat_engine.engine import (
    AC,
    AT_WILL,
    FORT,
    NO_TARGET,
    REF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    DamageApplied,
    DamageType,
    Healed,
    Hit,
    Melee,
    SurgeSpent,
    TurnEnd,
    When,
    Window,
    power,
)
from combat_engine.engine.query import taking_ongoing

#: The one type every burn in this file deals, as `query.taking_ongoing`
#: wants it.
_NECROTIC = frozenset({DamageType.NECROTIC})


def _lashes_out(c: Cast) -> None:
    """A melee basic attack on whichever ally is standing next to it.

    `c.within(1, side="ally")` leaves the diseased character out of its own
    pool, which is what the printed "an ally adjacent to it" means, and
    `who=c.me` names the swinger -- `on=` alone would have the board's
    chooser swing at nobody on a `NO_TARGET` row.
    """
    beside = next(iter(c.within(1, side="ally")), None)
    if beside is not None:
        c.basic(who=c.me, on=beside)


def _burns(c: Cast, amount: int) -> None:
    """Lay the save-ends burn, unless one of the same type is already on.

    `c.ongoing` enforces the printed "only the highest applies" by dropping
    the weaker burn -- but it still applies the hold carrying it, so a row
    re-laying on every tick of its own damage would leave a fresh empty
    save-ends effect behind each time. Asking first is the same answer with
    nothing left over.
    """
    if not taking_ongoing(c.world, c.me, _NECROTIC):
        c.ongoing(amount, DamageType.NECROTIC, on=c.me)


@power("x5_59", cls="disease", level=8, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_59(c: Cast) -> None:
    """Stages 2 and 3 are the same three penalties and the same slow, so one
    branch says both -- stage 3 is not stage 2 plus something, it is stage 2
    **without** the surge loss, which stages 1 and 2 print and stage 3 does
    not. One lost surge between the two stages rather than one each:
    `c.once_per_board` keys on the row's own ref, so the single call site
    under `in (1, 2)` cannot pay twice.

    Stage 3's extra paragraph is an extended-rest outcome -- death, or
    becoming a different creature -- which is the affliction track's
    business at a rest and not a stage effect this row lays on a board.
    """
    if c.stage in (1, 2):
        lost_surges(c, 1)

    if c.stage >= 2:
        c.penalty(AC, 2, on=c.me, until=When.ENCOUNTER)
        c.penalty(FORT, 2, on=c.me, until=When.ENCOUNTER)
        c.penalty(REF, 2, on=c.me, until=When.ENCOUNTER)
        c.slowed(on=c.me, until=When.ENCOUNTER)


@power("x5_93", cls="disease", level=8, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("story.npc_takeover()",))
def x5_93(c: Cast) -> None:
    """Five stages, not four, and each paragraph replaces the one above it:
    the Will penalty is printed at stage 1 and at no later stage, so the
    branches are exact rather than cumulative.

    `Bloodied` names its subject `actor`; `Hit` carries `attacker` and
    `target` and no `actor` at all, so the two watches ask different
    fields for the same creature.

    Stage 4 is dropped. The character stops being the party's at that point
    -- it is run by the DM, on its own stat block, and its attacks hand this
    same affliction on -- and nothing hands a player character over.
    """
    if c.stage == 1:
        c.penalty(WILL, 2, on=c.me, until=When.ENCOUNTER)

    if c.stage == 2:
        def when_bloodied(ev: Bloodied) -> None:
            if ev.actor == c.me:
                _lashes_out(c)

        c.watch(Bloodied, when_bloodied, until=When.ENCOUNTER, on=c.me)

    if c.stage == 3:
        def when_hit(ev: Hit) -> None:
            if ev.target == c.me:
                _lashes_out(c)

        c.watch(Hit, when_hit, until=When.ENCOUNTER, on=c.me)


@power("x5_22", cls="disease", level=10, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),)
def x5_22(c: Cast) -> None:
    """Two occasions per stage, and the second one is the same on both:
    being healed. Stage 2 adds becoming bloodied, stage 3 widens that to any
    damage at all, so the stages are written exclusively.

    **The lost surge is laid at every stage, not only at the one that
    prints it.** Stage 1's line is an Initial Effect that says "until
    cured", which outlives the stage that granted it -- the convention
    `mid_heroic.py` states and `x5_81`'s keyword is the other instance of.
    Writing it under `== 1` would have handed the surge back the moment the
    disease got worse. There is no branch because stage 0 is never armed.

    "Each time" is the trigger and not a licence to stack: the printed rule
    is one burn of a type at a time, which `_burns` keeps to.

    **"If this damage reduces the target to 0 hit points, it dies" is
    written now.** `c.kill` alone is a reduction to 0, which for a character
    is dying with death saves still to make -- `resolve._check_down` dies
    only when `hp <= health.dying_at`, and that is negative for a character.
    `c.kill(dead=True)` sets hit points to `dying_at` instead, so the one
    existing path to `resolve._die` is taken.

    **Gated on the burn being what did it**, which is the whole of "this
    damage": a sword finishing somebody who merely *has* the disease leaves
    them dying as usual.

    The discriminator is `DamageApplied.detail` -- *"what dealt it, a power
    ref where one did"* -- and **not** `ev.power`, which does not exist on
    this event. A first draft read `ev.power` through `getattr` with a
    default, so the gate was permanently true and the clause could never
    have fired: `engine/CLAUDE.md`'s "read the event before reading a field
    off it, a `getattr` with a default hides the mistake", exactly.
    """
    me = c.me
    lost_surges(c, 1)

    def dies_from_the_burn(ev: DamageApplied) -> None:
        """The burn, and only the burn, kills outright."""
        if ev.target != me or ev.detail != c.ref:
            return
        if DamageType.NECROTIC not in (getattr(ev, "dtypes", None) or
                                       (getattr(ev, "dtype", None),)):
            return
        from combat_engine.engine.components import Health

        health = c.world.get(me, Health)
        if health is not None and health.hp <= 0:
            c.kill(on=me, dead=True)

    c.watch(DamageApplied, dies_from_the_burn, until=When.ENCOUNTER, on=me)

    if c.stage == 2:
        def bloodied_burns(ev: Bloodied) -> None:
            if ev.actor == c.me:
                _burns(c, 5)

        def healing_burns(ev: Healed) -> None:
            if ev.target == c.me:
                _burns(c, 5)

        c.watch(Bloodied, bloodied_burns, until=When.ENCOUNTER, on=c.me)
        c.watch(Healed, healing_burns, until=When.ENCOUNTER, on=c.me)

    if c.stage == 3:
        def damage_burns(ev: DamageApplied) -> None:
            if ev.target == c.me:
                _burns(c, 15)

        def healing_burns_worse(ev: Healed) -> None:
            if ev.target == c.me:
                _burns(c, 15)

        c.watch(DamageApplied, damage_burns, until=When.ENCOUNTER, on=c.me)
        c.watch(Healed, healing_burns_worse, until=When.ENCOUNTER, on=c.me)


@power("x5_62", cls="disease", level=10, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("c.hp_ceiling()", "Effect.keywords"))
def x5_62(c: Cast) -> None:
    """The one disease here whose page stacks its stages: stage 3 says it
    suffers the effects of stage 2, and stage 2 reprints stage 1's penalty,
    so the branches are `>=`.

    **The half-heal is narrower than `c.half_healing`**, which halves every
    heal. The page halves what a *surge* restores, so the surge is latched
    off `SurgeSpent` -- announced before the hit points are handed over, and
    carrying the amount it is about to pay -- and the next `Healed` on this
    creature is the one it paid for. `ev.healed > 0` is what keeps a surge
    spent for nothing (the paladin's shape) from halving an unrelated heal
    afterwards.

    Two clauses dropped. A ceiling on the hit point total is not a smaller
    maximum -- the bloodied line would move with it -- and nothing holds one
    down, so clamping only the heals would leave a character walking in at
    full after a rest and quietly above the cap. And the aura is printed with
    a keyword, which an effect cannot carry, so a creature that should ignore
    it for being immune to that keyword pays anyway.
    """
    if c.stage >= 1:
        c.penalty(FORT, 2, on=c.me, until=When.ENCOUNTER)

    if c.stage >= 2:
        paid: list[int] = []

        def surge_taken(ev: SurgeSpent) -> None:
            if ev.actor == c.me and ev.healed > 0:
                paid.append(ev.healed)

        def halve(ev: Healed) -> None:
            if ev.target == c.me and paid:
                paid.pop()
                ev.amount //= 2

        c.watch(SurgeSpent, surge_taken, until=When.ENCOUNTER, on=c.me,
                window=Window.BEFORE)
        c.watch(Healed, halve, until=When.ENCOUNTER, on=c.me,
                window=Window.BEFORE)

    if c.stage >= 3:
        # "Cannot be deactivated", so no `sustain=` and nothing that drops
        # it. An aura does not affect the creature generating it, which is
        # what leaves `ev.actor == c.me` out below.
        c.aura(2, label=c.ref, until=When.ENCOUNTER, on=c.me)

        def pays_at_the_end(ev: TurnEnd) -> None:
            if ev.actor == c.me or not c.in_my_aura(ev.actor, label=c.ref):
                return
            c.spend_surge(on=ev.actor)

        c.watch(TurnEnd, pays_at_the_end, until=When.ENCOUNTER, on=c.me)


@power("x5_27", cls="disease", level=10, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_27(c: Cast) -> None:
    """x5_93's first three paragraphs at a higher level, and written the same
    way: each stage replaces the one above it, so the Will penalty is stage
    1's alone. This one stops at stage 3, so every paragraph it prints is
    laid."""
    if c.stage == 1:
        c.penalty(WILL, 2, on=c.me, until=When.ENCOUNTER)

    if c.stage == 2:
        def when_bloodied(ev: Bloodied) -> None:
            if ev.actor == c.me:
                _lashes_out(c)

        c.watch(Bloodied, when_bloodied, until=When.ENCOUNTER, on=c.me)

    if c.stage == 3:
        def when_hit(ev: Hit) -> None:
            if ev.target == c.me:
                _lashes_out(c)

        c.watch(Hit, when_hit, until=When.ENCOUNTER, on=c.me)
