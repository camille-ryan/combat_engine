"""Initiative, the round loop, and the action economy.

The economy's two awkward limits are here because they are not per-turn:
an immediate action is once per **round**, and an opportunity action is once
per **other creature's turn**. Both are stamped with what they were spent on
rather than reset at any single boundary, which is the only way a creature
that takes an opportunity attack on the fighter's turn still has one
available on the wizard's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Budget, Health, Initiative, Powers
from .conditions import rules
from .events import ActionSpent, Died, RoundEnd, RoundStart, SavingThrow, TurnEnd, TurnStart
from .query import active, alive, can_act, can_react, creatures, team
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
        world.bus.on(TurnEnd, self._death_saves)
        world.bus.on(Died, self._on_death)
        from .triggers import Triggers

        #: Offers a row when its printed trigger happens. Armed at `start`,
        #: because it walks the initiative order to decide who may answer.
        self.triggers = Triggers(world, self)

    # -- the clock -----------------------------------------------------------

    def start(self) -> None:
        self.order = self._roll_initiative()
        self.triggers.arm()
        self._arm_traits()
        self.started = True
        self.world.round = 1
        self.index = 0
        self.world.bus.emit(RoundStart(round=1))
        self._begin(self.order[0])

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
        from .components import Powers
        from .dsl import get, use
        from .types import ActionType

        for eid in self.order:
            known = self.world.get(eid, Powers)
            if known is None:
                continue
            for ref in known.all:
                p = get(ref)
                if p is not None and p.action is ActionType.NONE:
                    use(self.world, eid, ref, spend=True)

    def _roll_initiative(self) -> list[int]:
        rolls: list[tuple[int, int, int, int]] = []
        for eid in creatures(self.world):
            init = self.world.get(eid, Initiative) or self.world.add(eid, Initiative())
            from .query import level_term

            init.rolled = (
                self.world.rng.d20().total
                + init.bonus
                + level_term(self.world, eid, init.scale)
            )
            # Ties go to the higher modifier, then to spawn order, so two runs
            # of the same seed produce the same order.
            rolls.append((-init.rolled, -init.bonus, eid, eid))
        return [eid for _, _, eid, _ in sorted(rolls)]

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
        return self._splice(eid, init.rolled)

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
        sides = {team(self.world, e) for e in creatures(self.world) if alive(self.world, e)}
        sides.discard(Team.NEUTRAL)
        sides.discard(None)
        return len(sides) < 2

    @property
    def winner(self) -> Team | None:
        sides = {team(self.world, e) for e in creatures(self.world) if alive(self.world, e)}
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
        self.world.bus.emit(
            SavingThrow(
                actor=ev.actor, against="death", natural=roll.total, bonus=0, saved=saved
            )
        )
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
