"""How long things last.

One `Effect` is one thing a power did that has not finished happening: a
condition, some modifiers, a relation, ongoing damage, a registered trigger,
or several at once. It knows how to take itself back apart, so ending it is
never a matter of remembering what it did.

**The latch.** "Until the end of your next turn" is the one duration engines
get wrong. Applied on somebody else's turn it expires at the end of your next
turn -- the very next one. Applied on *your own* turn, your next turn is the
one after the current one, so the current turn's end has to be skipped.
`latch` is that skipped boundary, and it is set from whose turn it is at the
moment of application. Without it, half of 4e's effects expire a full turn
early and every fight quietly reads wrong.

The start-of-turn durations need no latch: your current turn has already
started, so the next `TurnStart` naming you is already your next turn.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from .components import Conditions, Mod, Mods
from .events import (
    ConditionApplied,
    ConditionEnded,
    EffectExpired,
    SavingThrow,
    TurnEnd,
    TurnStart,
)
from .types import Condition, DamageType, Relation

if TYPE_CHECKING:
    from .ecs import World
    from .events import Sub


class When(StrEnum):
    INSTANT = "instant"
    EONT = "end of source's next turn"
    SONT = "start of source's next turn"
    EOTNT = "end of target's next turn"
    SOTNT = "start of target's next turn"
    SAVE_ENDS = "save ends"
    ENCOUNTER = "end of encounter"
    STANCE = "stance"
    SUSTAIN = "sustain"


#: Durations whose clock is the creature the effect sits on rather than the
#: creature that applied it.
_TARGET_CLOCKED = {When.EOTNT, When.SOTNT, When.SAVE_ENDS}

#: Durations that no turn boundary will ever end. If the creature holding one
#: up dies, nothing is coming to clear it, so death has to.
_UNREACHABLE = {When.ENCOUNTER, When.STANCE, When.SUSTAIN}


@dataclass
class Effect:
    id: int
    label: str
    owner: int
    source: int
    when: When
    clock: int
    latch: bool = False
    conditions: tuple[Condition, ...] = ()
    mods: list[tuple[int, Mod]] = field(default_factory=list)
    relations: list[tuple[Relation, int, int]] = field(default_factory=list)
    ongoing: tuple[int, DamageType] | None = None
    save_mod: int = 0
    #: Runs on a failed save. This is how "and worsens" powers are written.
    escalate: Callable[[Effect], None] | None = None
    subs: list[Sub] = field(default_factory=list)
    on_end: list[Callable[[], None]] = field(default_factory=list)
    sustained: int = -1
    ended: bool = False

    def __str__(self) -> str:
        bits = [self.label or "effect", self.when.value]
        if self.ongoing:
            bits.append(f"ongoing {self.ongoing[0]} {self.ongoing[1]}")
        return f"e{self.id}[{', '.join(bits)}]"


class Effects:
    """Every live effect, and the turn boundaries that end them."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.live: dict[int, Effect] = {}
        self._next = 0
        world.bus.on(TurnStart, self._on_turn_start)
        world.bus.on(TurnEnd, self._on_turn_end)

    # -- applying ------------------------------------------------------------

    def apply(
        self,
        owner: int,
        source: int,
        when: When,
        *,
        label: str = "",
        conditions: Iterable[Condition] = (),
        mods: Iterable[tuple[int, Mod]] = (),
        relations: Iterable[tuple[Relation, int, int]] = (),
        ongoing: tuple[int, DamageType] | None = None,
        save_mod: int = 0,
        escalate: Callable[[Effect], None] | None = None,
        subs: Iterable[Sub] = (),
        on_end: Iterable[Callable[[], None]] = (),
    ) -> Effect:
        self._next += 1
        clock = owner if when in _TARGET_CLOCKED else source
        eff = Effect(
            id=self._next,
            label=label,
            owner=owner,
            source=source,
            when=when,
            clock=clock,
            latch=(when in (When.EONT, When.EOTNT) and self.world.turn == clock),
            conditions=tuple(conditions),
            mods=list(mods),
            relations=list(relations),
            ongoing=ongoing,
            save_mod=save_mod,
            escalate=escalate,
            subs=list(subs),
            on_end=list(on_end),
            sustained=self.world.round,
        )
        self.live[eff.id] = eff

        conds = self.world.get(owner, Conditions)
        for c in eff.conditions:
            if conds is not None and conds.add(c):
                self.world.bus.emit(
                    ConditionApplied(
                        source=source, target=owner, condition=c, duration=when.value
                    )
                )
        for eid, mod in eff.mods:
            holder = self.world.get(eid, Mods)
            if holder is None:
                holder = self.world.add(eid, Mods())
            holder.items.append(mod)
        for kind, s, t in eff.relations:
            self.world.relations.set(kind, s, t)

        if when is When.INSTANT:
            self.end(eff, "instant")
        return eff

    # -- ending --------------------------------------------------------------

    def end(self, eff: Effect, why: str = "expired") -> None:
        if eff.ended:
            return
        eff.ended = True
        self.live.pop(eff.id, None)

        conds = self.world.get(eff.owner, Conditions)
        for c in eff.conditions:
            if conds is not None and conds.remove(c):
                self.world.bus.emit(ConditionEnded(target=eff.owner, condition=c, why=why))
        for eid, mod in eff.mods:
            holder = self.world.get(eid, Mods)
            if holder is not None and mod in holder.items:
                holder.items.remove(mod)
        for kind, s, t in eff.relations:
            self.world.relations.clear(kind, s, t, why)
        for sub in eff.subs:
            self.world.bus.off(sub)
        for fn in eff.on_end:
            fn()
        if eff.when is not When.INSTANT:
            self.world.bus.emit(EffectExpired(actor=eff.owner, what=str(eff), why=why))

    def forget(self, eid: int, why: str = "left play") -> None:
        """End everything `eid` is either end of. Total removal only."""
        for eff in list(self.live.values()):
            if eff.owner == eid or eff.source == eid or eff.clock == eid:
                self.end(eff, why)

    def bereave(self, eid: int, why: str = "died") -> None:
        """Clean up after a creature's death without cutting durations short.

        A daze that lasts "until the end of your next turn" does **not** end
        the instant you are killed. It ends when you would have acted -- the
        effect runs to your slot in the initiative order and expires there.
        `Encounter` keeps the dead in the order and ticks a silent turn for
        exactly this, so a turn-clocked effect needs no help here.

        What does need help is everything with no clock to reach:

        * effects *on* the corpse, which are meaningless now;
        * effects it was the source of that expire at the end of the
          encounter, on a stance, or on being sustained -- nothing will ever
          come to end those, so they would hang forever.

        A save-ends effect is clocked on whoever is suffering it, so the
        source dying is none of its business either way.
        """
        for eff in list(self.live.values()):
            on_the_corpse = eff.owner == eid
            nothing_will_end_it = eff.source == eid and eff.when in _UNREACHABLE
            if on_the_corpse or nothing_will_end_it:
                self.end(eff, why)

    def end_encounter(self) -> None:
        for eff in list(self.live.values()):
            self.end(eff, "encounter over")

    def of(self, owner: int) -> list[Effect]:
        return [e for e in self.live.values() if e.owner == owner]

    def clocked_on(self, eid: int) -> list[Effect]:
        """Live effects waiting on this creature's turn boundaries."""
        return [
            e
            for e in self.live.values()
            if e.clock == eid and e.when not in _UNREACHABLE and e.when is not When.INSTANT
        ]

    def carries(self, kind: Relation, source: int, target: int) -> bool:
        """Is this relation held up by a live effect that will end it?"""
        return any(
            (kind, source, target) in eff.relations for eff in self.live.values()
        )

    def sustain(self, eff: Effect) -> None:
        eff.sustained = self.world.round

    # -- the clock -----------------------------------------------------------

    def _on_turn_start(self, ev: TurnStart) -> None:
        for eff in list(self.live.values()):
            if eff.ongoing is not None and eff.owner == ev.actor:
                amount, dtype = eff.ongoing
                self.world.damage(eff.source, eff.owner, amount, dtype, detail=str(eff))
            if eff.when is When.SONT and eff.clock == ev.actor:
                self.end(eff, "start of turn")
            elif eff.when is When.SOTNT and eff.clock == ev.actor:
                if eff.latch:
                    eff.latch = False
                else:
                    self.end(eff, "start of turn")

    def _on_turn_end(self, ev: TurnEnd) -> None:
        for eff in list(self.live.values()):
            if eff.clock != ev.actor:
                continue
            if eff.when in (When.EONT, When.EOTNT):
                if eff.latch:
                    eff.latch = False
                else:
                    self.end(eff, "end of turn")
            elif eff.when is When.SAVE_ENDS:
                self._save(eff)
            elif eff.when is When.SUSTAIN and eff.sustained < self.world.round:
                self.end(eff, "not sustained")

    def _save(self, eff: Effect) -> None:
        holder = self.world.get(eff.owner, Mods)
        bonus = eff.save_mod + (holder.total("save") if holder else 0)
        roll = self.world.rng.d20()
        saved = roll.total + bonus >= 10
        self.world.bus.emit(
            SavingThrow(
                actor=eff.owner,
                against=str(eff),
                natural=roll.total,
                bonus=bonus,
                saved=saved,
            )
        )
        if saved:
            self.end(eff, "saved")
        elif eff.escalate is not None:
            eff.escalate(eff)
