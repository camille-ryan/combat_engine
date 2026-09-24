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
from .events import Died, RoundEnd, RoundStart, SavingThrow, TurnEnd, TurnStart
from .query import active, alive, can_act, can_react, creatures, team
from .types import DOWNGRADES, ActionType, Condition, Team, Usage

if TYPE_CHECKING:
    from .ecs import World


class Encounter:
    """One fight. Owns the clock; owns nothing else."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.order: list[int] = []
        self.index = 0
        self.started = False
        self.finished = False
        world.bus.on(TurnEnd, self._death_saves)
        world.bus.on(Died, self._on_death)

    # -- the clock -----------------------------------------------------------

    def start(self) -> None:
        self.order = self._roll_initiative()
        self.started = True
        self.world.round = 1
        self.index = 0
        self.world.bus.emit(RoundStart(round=1))
        self._begin(self.order[0])

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
        if self._one_action(eid):
            return budget.standard + budget.move + budget.minor > 0
        return any(getattr(budget, slot.value) > 0 for slot in DOWNGRADES[what])

    def spend(self, eid: int, what: ActionType) -> bool:
        """Take the action if it is available. Returns False if it was not."""
        if not self.can_spend(eid, what):
            return False
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
        slot = self.order.index(self.world.turn) if self.world.turn in self.order else 0
        return self.world.round * 1000 + slot

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
