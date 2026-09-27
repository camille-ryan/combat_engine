"""Initiative, the round loop, and the action economy.

The economy's two awkward limits are here because they are not per-turn:
an immediate action is once per **round**, and an opportunity action is once
per **other creature's turn**. Both are stamped with what they were spent on
rather than reset at any single boundary, which is the only way a creature
that takes an opportunity attack on the fighter's turn still has one
available on the wizard's.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .components import Budget, Health, Initiative, Powers
from .conditions import rules
from .durations import When
from .events import (
    ActionSpent,
    Died,
    InitiativeRolled,
    RoundEnd,
    RoundStart,
    SavingThrow,
    TurnEnd,
    TurnStart,
)
from .query import active, alive, can_act, can_react, combatants, team
from .types import DOWNGRADES, ActionType, Condition, Team, Usage

if TYPE_CHECKING:
    from .ecs import World


class Encounter:
    """One fight. Owns the clock; owns nothing else."""

    def __init__(self, world: World) -> None:
        self.world = world
        world.encounter = self
        self.order: list[int] = []
        self.index = 0
        self.started = False
        self.finished = False
        #: Whether round 1 is a surprise round. See `start`.
        self._surprise = False
        world.bus.on(TurnEnd, self._death_saves)
        world.bus.on(Died, self._on_death)
        from .triggers import Triggers

        #: Offers a row when its printed trigger happens. Armed at `start`,
        #: because it walks the initiative order to decide who may answer.
        self.triggers = Triggers(world, self)

    # -- the clock -----------------------------------------------------------

    def start(self, surprised: Iterable[int] = ()) -> None:
        """Begin the fight. `surprised` is whoever did not see it coming.

        **There was no surprise round at all**, which is why a rogue could
        never open a fight with a sneak attack -- and why eight content
        rows that read `Condition.SURPRISED` were permanently false.
        Every occurrence of it in the tree was a reader or a cure; nothing
        anywhere applied it.

        The condition already says what being surprised means -- grants
        combat advantage, cannot act, no reactions -- so the round falls
        out of applying it: the surprised take their turn and can do
        nothing with it, and it lifts when the round does.
        """
        # Armed *before* the rolls, so a row triggered on `InitiativeRolled`
        # can hear the opening ones. Arming after meant the only initiative
        # rolls a row could ever answer were rerolls, which is not what any
        # printed line says.
        self.triggers.arm()
        self._refresh_pools()
        self.order = self._roll_initiative()
        self._arm_traits()
        self.started = True
        self.world.round = 1
        self.index = 0
        for eid in surprised:
            self.world.effects.apply(
                eid, eid, When.ENCOUNTER, label="surprised",
                conditions=[Condition.SURPRISED],
            )
        self._surprise = bool(surprised)
        self.world.bus.emit(RoundStart(round=1))
        self._begin(self.order[0])

    def _end_surprise(self) -> None:
        """The surprise round is over; everybody is in the fight now."""
        if not self._surprise:
            return
        self._surprise = False
        for eff in list(self.world.effects.live.values()):
            if eff.label == "surprised":
                self.world.effects.end(eff, "the surprise round is over")

    def _refresh_pools(self) -> None:
        """Power points come back and the action-point limit resets.

        Both are per-encounter and both would otherwise only ever be right
        for the first fight of a session.
        """
        from .components import ActionPoints, PowerPoints

        for _, pool in self.world.each(PowerPoints):
            pool.refresh()
        for _, points in self.world.each(ActionPoints):
            points.refresh()

    def _arm_traits(self) -> None:
        """Turn on everything that is simply *true* of a creature.

        A trait -- `action=NONE` -- is not something anybody does. A rogue's
        extra damage, a fighter's answer to being ignored, a monster's aura:
        they are in force from the moment the fight starts and no turn is
        spent on them.

        Until this existed a trait was an action like any other, and the
        policy re-took it every turn it had a spare moment. Seven rounds in,
        the rogue had armed its extra damage seventy-one times -- seventy-one
        separate watchers, each with its own once-a-round latch, each paying
        out. Arming once, here, is both the rule and the fix.
        """

        # A copy of the order: a trait may splice into it -- `c.extra_turn`
        # during arming is how several solos work -- and inserting at or
        # before the cursor made the loop revisit a creature. Harmless only
        # because an encounter-usage trait is refused the second time.
        for eid in list(self.order):
            self.arm_traits_of(eid)

    def arm_traits_of(self, eid: int) -> None:
        """Turn on one creature's traits.

        Split out because `join` needs it: a creature that arrives mid-fight
        went into the order with every `action=NONE` row silently unarmed,
        so a summoned monster had no aura, no regeneration and none of the
        things that are simply true of it. Every summon in the tree was
        quietly weaker than its stat block.
        """
        from .components import Powers
        from .dsl import get, use
        from .types import ActionType

        known = self.world.get(eid, Powers)
        if known is None:
            return
        for ref in known.all:
            p = get(ref)
            # A trait is simply *true*: no action and nothing to wait for.
            # A no-action row that declares a trigger is a different thing
            # -- it happens when its trigger does -- and arming it at the
            # start would fire it once, out of nowhere, and never again.
            if p is not None and p.action is ActionType.NONE and not p.triggers:
                use(self.world, eid, ref, spend=True)

    def _roll_initiative(self) -> list[int]:
        """Everybody rolls, then the rolls are announced, then they are read.

        Three beats rather than one, because "you and each ally gain +5 to
        your initiative check" answers *one* creature's roll and reaches for
        everybody's. Announcing each roll as it was made meant half the
        party had not rolled yet, so the bonus landed on a number that was
        then overwritten -- and the half that had rolled were already in the
        sort, which was built from a local copy. The row read as working and
        moved nobody.
        """
        from .query import level_term

        order = list(combatants(self.world))
        for eid in order:
            init = self.world.get(eid, Initiative) or self.world.add(eid, Initiative())
            init.rolled = (
                self.world.rng.d20().total
                + init.bonus
                + level_term(self.world, eid, init.scale)
            )
        # The dispatcher offers an event to `encounter.order` and to nobody
        # else, and at this point in `start` that list is still empty -- so
        # arming the triggers before the rolls, which the comment there says
        # is done so the opening rolls can be answered, put every row of
        # that shape in front of an empty room. Four were written against
        # it and none had ever fired. Provisional, in roll order; `start`
        # overwrites it with the sort a beat later.
        self.order = list(order)
        for eid in order:
            init = self.world.need(eid, Initiative)
            self.world.bus.emit(InitiativeRolled(actor=eid, rolled=init.rolled))
        # Read back off the component, not off what was announced, so
        # `c.initiative` reaches the order it exists to change. Ties go to
        # the higher modifier, then to spawn order, so two runs of the same
        # seed produce the same order.
        rolls: list[tuple[int, int, int, int]] = []
        for eid in order:
            init = self.world.need(eid, Initiative)
            rolls.append((-init.rolled, -init.bonus, eid, eid))
        return [eid for _, _, eid, _ in sorted(rolls)]

    def adjust_initiative(self, eid: int, amount: int) -> int:
        """Move a creature up or down the order without rolling again.

        "Each target gains a +10 bonus to his or her initiative check" is a
        modifier to a number that has already been rolled, and there was
        nowhere to put it: `Initiative.bonus` is read *before* the d20, and
        setting `InitiativeRolled.rolled` from a listener changes a copy the
        sort never looks at. So it goes on the component, and during the
        opening rolls that is enough -- `_roll_initiative` reads the
        component back. Later, the order already exists, so the creature is
        lifted out and spliced in again. The turn in progress keeps its
        slot, because moving the creature that is acting would end its turn
        somewhere else.
        """
        init = self.world.get(eid, Initiative) or self.world.add(eid, Initiative())
        init.rolled += amount
        # `self.started` is set *after* `_arm_traits`, so a trait whose whole
        # content is "you and each ally gain +2 to initiative" bumped the
        # number and never touched the order -- which is the only thing that
        # number is for. What the guard is really protecting is the turn in
        # progress, and during arming there is none.
        if self.order and eid in self.order:
            was = self.order.index(eid)
            if not self.started or was != self.index:
                self.order.pop(was)
                if was < self.index:
                    self.index -= 1
                self._splice(eid, init.rolled)
        return init.rolled

    def swap_initiative(self, a: int, b: int) -> bool:
        """Two creatures change places in the initiative order.

        The counts go with the slots, so anything spliced in later still
        sorts against the number each creature is now acting on.

        When one of them is the creature whose turn it is, the slot being
        played has changed owner, and the cursor steps back so that
        `advance` plays that slot again for its new occupant. That is the
        printed "the ally takes his or her next turn immediately, even if he
        or she has already acted during this round"; the creature swapped
        out then acts where the ally would have.
        """
        if a == b or a not in self.order or b not in self.order:
            return False
        i, j = self.order.index(a), self.order.index(b)
        self.order[i], self.order[j] = self.order[j], self.order[i]
        first = self.world.get(a, Initiative) or self.world.add(a, Initiative())
        second = self.world.get(b, Initiative) or self.world.add(b, Initiative())
        first.rolled, second.rolled = second.rolled, first.rolled
        if self.started and self.index in (i, j):
            self.index -= 1
        return True

    def reroll_initiative(self, eid: int) -> int:
        """Roll again and move the creature to its new place.

        The turn in progress keeps its slot: `_splice` shifts the cursor
        when it inserts at or before it, and the creature is lifted out
        first so it does not end up in the order twice.
        """
        from .query import level_term

        init = self.world.get(eid, Initiative) or self.world.add(eid, Initiative())
        was = self.order.index(eid) if eid in self.order else None
        if was is not None:
            self.order.pop(was)
            if was < self.index:
                self.index -= 1
        init.rolled = (
            self.world.rng.d20().total
            + init.bonus
            + level_term(self.world, eid, init.scale)
        )
        self.world.bus.emit(InitiativeRolled(actor=eid, rolled=init.rolled))
        self._splice(eid, init.rolled)
        return init.rolled

    def join(self, eid: int) -> int:
        """Put a creature that was not here at the start into the order.

        Rolls its initiative and splices it in by that, so it acts where it
        belongs rather than wherever it happened to arrive. Anything spawned
        mid-fight was simply absent from the order before this, which meant
        it never got a turn at all.

        Returns the slot it landed in.
        """
        from .query import level_term

        if eid in self.order:
            return self.order.index(eid)
        init = self.world.get(eid, Initiative) or self.world.add(eid, Initiative())
        init.rolled = (
            self.world.rng.d20().total
            + init.bonus
            + level_term(self.world, eid, init.scale)
        )
        where = self._splice(eid, init.rolled)
        self.arm_traits_of(eid)
        return where

    def extra_turn(self, eid: int, at: int) -> int:
        """Give a creature a *second* slot, at that initiative count.

        A solo acting twice a round is one creature in two places in the
        order, which is what the printed rule describes. Duplicated rather
        than special-cased, so every reader of the order keeps working.
        """
        return self._splice(eid, at)

    def _splice(self, eid: int, rolled: int) -> int:
        """Insert a slot by initiative, keeping the current turn's place."""
        where = len(self.order)
        for i, other in enumerate(self.order):
            init = self.world.get(other, Initiative)
            if init is not None and init.rolled < rolled:
                where = i
                break
        self.order.insert(where, eid)
        # The creature whose turn it is must keep its slot. Inserting at or
        # before the cursor shifts everything after it along by one, and
        # without this the newcomer would steal the turn in progress.
        if where <= self.index:
            self.index += 1
        return where

    def _begin(self, eid: int) -> None:
        self.world.turn = eid
        budget = self.world.get(eid, Budget) or self.world.add(eid, Budget())
        budget.refresh()
        self.world.bus.emit(TurnStart(actor=eid, round=self.world.round))

    def end_turn(self) -> None:
        eid = self.world.turn
        if eid is None:
            return
        from .movement import settle

        settle(self.world, eid)  # a flyer comes down before the turn is over
        _uncommanded(self.world, eid)
        self.world.bus.emit(TurnEnd(actor=eid, round=self.world.round))
        self.world.turn = None

    def advance(self) -> int | None:
        """End the current turn and begin the next living creature's.

        Returns whose turn it now is, or None when the fight is over.
        """
        if not self.started or self.finished:
            return None
        self.end_turn()
        if self.over:
            self.finish()
            return None
        for _ in range(len(self.order) + 1):
            self.index += 1
            if self.index >= len(self.order):
                self.index = 0
                self.world.bus.emit(RoundEnd(round=self.world.round))
                self._end_surprise()
                self.world.round += 1
                self.world.bus.emit(RoundStart(round=self.world.round))
            nxt = self.order[self.index]
            if alive(self.world, nxt):
                self._begin(nxt)
                return nxt
            self._ghost(nxt)
        self.finish()
        return None

    def _ghost(self, eid: int) -> None:
        """Tick a dead creature's slot without giving it a turn.

        A creature killed after dazing somebody "until the end of your next
        turn" does not release that daze by dying -- the daze lasts until the
        point it *would have* acted. The dead therefore keep their place in
        the order, and their slot still opens and closes so that anything
        measured against it can come to an end.

        Nobody acts on a ghost turn. `world.turn` is left alone, so nothing
        reads it as the dead creature's turn, and `ghost=True` is on both
        events so the interface and any policy can ignore the pair outright.
        """
        if not self.world.effects.clocked_on(eid):
            return
        self.world.bus.emit(TurnStart(actor=eid, round=self.world.round, ghost=True))
        self.world.bus.emit(TurnEnd(actor=eid, round=self.world.round, ghost=True))

    @property
    def over(self) -> bool:
        sides = {team(self.world, e) for e in combatants(self.world) if alive(self.world, e)}
        sides.discard(Team.NEUTRAL)
        sides.discard(None)
        return len(sides) < 2

    @property
    def winner(self) -> Team | None:
        sides = {team(self.world, e) for e in combatants(self.world) if alive(self.world, e)}
        sides.discard(Team.NEUTRAL)
        sides.discard(None)
        return next(iter(sides)) if len(sides) == 1 else None

    def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.world.turn = None
        self.triggers.disarm()
        self.world.effects.end_encounter()

    # -- spending actions ----------------------------------------------------

    def can_spend(self, eid: int, what: ActionType) -> bool:
        budget = self.world.get(eid, Budget)
        if budget is None:
            return False
        if what in (ActionType.FREE, ActionType.NONE):
            return True
        if what in (ActionType.IMMEDIATE_INTERRUPT, ActionType.IMMEDIATE_REACTION):
            return can_react(self.world, eid) and budget.immediate_round != self.world.round
        if what is ActionType.OPPORTUNITY:
            return can_react(self.world, eid) and budget.opportunity_turn != self._turn_stamp()
        if self.world.turn != eid or not can_act(self.world, eid):
            return False
        if what is ActionType.STANDARD and any(
            rules(c).no_standard for c in active(self.world, eid)
        ):
            return False
        if self._one_action(eid):
            return budget.standard + budget.move + budget.minor > 0
        return any(getattr(budget, slot.value) > 0 for slot in DOWNGRADES[what])

    def spend(self, eid: int, what: ActionType) -> bool:
        """Take the action if it is available. Returns False if it was not."""
        if not self.can_spend(eid, what):
            return False
        self.world.bus.emit(ActionSpent(actor=eid, cost=what))
        budget = self.world.need(eid, Budget)
        if what in (ActionType.FREE, ActionType.NONE):
            return True
        if what in (ActionType.IMMEDIATE_INTERRUPT, ActionType.IMMEDIATE_REACTION):
            budget.immediate_round = self.world.round
            return True
        if what is ActionType.OPPORTUNITY:
            budget.opportunity_turn = self._turn_stamp()
            return True
        if self._one_action(eid):
            # Dazed: one action of any kind, so spending it empties the turn.
            budget.standard = budget.move = budget.minor = 0
            return True
        # A standard may be spent as a move and a move as a minor, so take the
        # cheapest slot that can pay and leave the richer ones alone.
        for slot in DOWNGRADES[what]:
            if getattr(budget, slot.value) > 0:
                setattr(budget, slot.value, getattr(budget, slot.value) - 1)
                return True
        return False

    def _one_action(self, eid: int) -> bool:
        from .conditions import rules

        return any(rules(c).one_action for c in active(self.world, eid))

    def _turn_stamp(self) -> int:
        """Identifies one creature's turn. Opportunity actions refresh on it."""
        # The slot being played, not the first slot this creature owns. A
        # solo with a second turn holds two, and looking the eid up gave
        # both of them the same stamp -- so its opportunity action never
        # refreshed on the second one.
        return self.world.round * 1000 + self.index

    # -- dying ---------------------------------------------------------------

    def _death_saves(self, ev: TurnEnd) -> None:
        from .query import is_

        if not is_(self.world, ev.actor, Condition.DYING):
            return
        health = self.world.need(ev.actor, Health)
        roll = self.world.rng.d20()
        saved = roll.total >= 10
        # Read back, like every other saving throw. A death save is the
        # one somebody is most likely to print a rider on.
        rolled = self.world.bus.emit(
            SavingThrow(
                actor=ev.actor, against="death", natural=roll.total, bonus=0, saved=saved
            )
        )
        saved = rolled.saved
        if saved:
            if roll.total == 20:
                self.world.heal(ev.actor, ev.actor, health.surge_value)
            return
        health.failures += 1
        if health.failures >= 3:
            from .resolve import _die

            _die(self.world, ev.actor)

    def _on_death(self, ev: Died) -> None:
        if ev.actor in self.order and self.world.turn == ev.actor:
            pass  # the turn ends normally; `advance` skips the dead


def refresh_encounter_powers(world: World) -> None:
    """Short rest: encounter powers come back, daily ones do not."""
    from .dsl import get

    for _, powers in world.each(Powers):
        for ref in list(powers.used):
            declared = get(ref)
            if declared is None or declared.usage is not Usage.DAILY:
                powers.restore(ref)


def _uncommanded(world: World, owner: int) -> None:
    """Run the instinctive effect of every summon left to its own devices.

    **Every summon block prints this and none of them could reach it.**
    "If you haven't given it any commands by the end of your turn, it
    ..." -- ten druid blocks say so, and the behaviour was written and
    then openable only by the one utility row that spends an action to
    provoke it. A creature that its owner ignored simply stood there.

    Before `TurnEnd`, so a row answering the end of a turn sees what the
    summon did rather than the board as the owner left it.
    """
    from .cast import Cast
    from .components import Companion

    for eid in sorted(world.having(Companion)):
        mine = world.get(eid, Companion)
        if mine is None or mine.owner != owner or mine.commanded == world.round:
            continue
        Cast(world=world, me=owner, ref=mine.ref).instinctive(eid)

