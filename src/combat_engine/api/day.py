"""The adventuring day, arcade mode.

**Parallel to the story engine, not part of it.** Camille's framing: this is
a number of single combats the user asks for, each built to its own share of
the printed XP budget, with a rest between. The story engine is the other
thing that wants a day and wants it for different reasons -- a campaign that
remembers -- so the two are kept apart deliberately and only meet at
`story.budget`, which is the printed rule either way.

Nothing here is a new notion of difficulty. A leg's `scale` is a multiple of
`story.budget(level)`, which reads what the monsters are actually worth out
of the database, so a 1.25 leg is 25% more of the same currency rather than
a separate dial.
"""

from __future__ import annotations

#: The softest and hardest legs of the default curve.
OPENER = 0.75
FINALE = 1.25


def scales(count: int) -> list[float]:
    """The default difficulty curve for a day of `count` fights.

    A soft opener, a hard finale, and standard fights between -- so four legs
    come out `0.75, 1, 1, 1.25`, which is Camille's default and totals four
    times a standard encounter, the printed shape of an adventuring day.

    **Padded in the middle rather than stretched.** Camille's call: a longer
    day keeps one soft fight and one hard one and adds standard ones, rather
    than spreading the curve thinner. It matters less than it looks because
    the user sets the difficulties -- this is the starting point the page
    offers, not a rule.

    One fight is standard, because an opener with no finale after it is not
    an opener; two are the opener and the finale with nothing between.
    """
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    if count == 2:
        return [OPENER, FINALE]
    return [OPENER, *([1.0] * (count - 2)), FINALE]


# -- the day itself ---------------------------------------------------------
#
# **A `Day` owns a `Party` and builds one `Session` per leg.** It does not
# own a `World`: `story`'s own note settles that -- a world cannot be copied,
# because bus subscriptions close over it, so a long-lived one could not be
# snapshotted or forked, and world-per-fight is the intended shape rather
# than a limitation. The day carries the *wear* across instead, which is what
# `story.harvest` and `Party.rest` are for.

import threading  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import TYPE_CHECKING  # noqa: E402

from combat_engine import story  # noqa: E402

from . import dto  # noqa: E402

if TYPE_CHECKING:
    from .session import Session

#: What a short rest is between legs. A day's fights are minutes apart; an
#: extended rest would end the day, which is the thing being measured.
BETWEEN_LEGS_EXTENDED = False


@dataclass
class _Leg:
    """One fight's record. The DTO is rendered off this, not stored."""

    index: int
    scale: float
    status: str = "pending"
    rounds: int = 0
    entering: list[dto.DaySheetDTO] = field(default_factory=list)
    ended: list[dto.DaySheetDTO] = field(default_factory=list)
    rested: list[dto.DaySheetDTO] = field(default_factory=list)
    rest_text: str = ""
    exhausted: bool = False
    #: `max_hp`/`max_surges` per wire id, captured off the world while there
    #: was one. `story.Sheet` carries `max_hp` but **not** a surge maximum,
    #: and `rested` is read off the sheets after the world is gone -- so the
    #: ceiling has to be remembered here or the surge pips have nothing to
    #: draw a track for.
    ceilings: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: The party's entity ids, **pinned when the board was fielded**, in the
    #: order `story.harvest` matches sheets by. Pinned rather than re-derived
    #: because the PC side grows: a familiar is a `Team.PC` creature with
    #: `Health`, so reading the side again at the end of the fight gave five
    #: rows against four sheets -- caught by `api_smoke`'s roll call on its
    #: first run. At fielding time the side *is* the party, with nothing
    #: summoned yet, so this is the one moment the list is exactly right.
    roster: list[int] = field(default_factory=list)


@dataclass
class Day:
    """A number of single combats, each built to its share of the budget."""

    id: str
    seed: int
    level: int
    scaling: str
    pcs: list[str] | None
    scales: list[float]
    party: story.Party
    legs: list[_Leg]
    leg: int = 0
    #: The session being played, if one is. Cleared when its fight ends.
    session_id: str = ""
    finished: bool = False
    outcome: str = ""
    #: **Held across settling and across building a leg.** FastAPI runs a
    #: `def` endpoint in a threadpool, and the page polls `/api/day/{id}`
    #: while a fight is on -- so two reads can arrive together, both find a
    #: finished fight, and both harvest and rest. The guards in `settle` are
    #: checked before the work and cleared after it, which is exactly the
    #: window. A party resting twice between legs is a day twice as long as
    #: the one the player asked for.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- building ----------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        seed: int,
        level: int = 1,
        scaling: str = "full",
        pcs: list[str] | None = None,
        want: list[float] | None = None,
    ) -> Day:
        """Deal the party and set out the legs. No fight is built yet.

        `want` is the page's four boxes. Empty or absent falls back to
        `scales(4)`, which is the same curve those boxes ship pre-filled
        with -- so the default lives in two places on purpose, and they are
        asserted equal rather than one being derived from the other across
        the wire.
        """
        import uuid

        curve = [float(x) for x in (want or [])] or scales(4)
        if not curve:
            raise ValueError("a day needs at least one fight")
        if any(x <= 0 for x in curve):
            raise ValueError("a fight's budget multiplier must be positive")
        party = story.Party.of(pcs or list(story.PARTY), level, seed=seed)
        return cls(
            id=uuid.uuid4().hex[:12],
            seed=seed,
            level=level,
            scaling=scaling,
            pcs=list(pcs) if pcs else None,
            scales=curve,
            party=party,
            legs=[_Leg(index=i, scale=s) for i, s in enumerate(curve)],
        )

    def build_leg(self) -> Session:
        with self.lock:
            return self._build_leg()

    def _build_leg(self) -> Session:
        """Field the current leg and hand back its session.

        **A seed per leg, derived from the day's.** Every leg sharing one seed
        would field the same monsters four times, and a day of one fight
        repeated is not a day.
        """
        from .session import Session

        if self.finished:
            raise ValueError("the day is over")
        if self.session_id:
            raise ValueError("a fight is already in progress")
        here = self.legs[self.leg]
        # **Snapshotted through the hook, not off the returned session.**
        # `Session.create` runs the monsters' turns before it returns, so
        # reading the party afterwards gives the party *after* the enemies'
        # first round. Leg 1 then appeared to walk in worse than it had
        # rested to, which reads as the rest being undone.
        session = Session.create(
            seed=self.seed + self.leg + 1,
            level=self.level,
            scaling=self.scaling,
            pcs=self.pcs,
            party=self.party,
            scale=here.scale,
            on_fielded=lambda s: self._fielded(s, here),
        )
        self.session_id = session.id
        here.status = "fighting"
        return session

    def _fielded(self, session: Session, leg: _Leg) -> None:
        """Called the moment the board exists, before anybody has acted.

        Two things happen here and both have to, because this is the only
        moment that is both after the world is built and before a turn is
        taken.
        """
        # **How many milestones the party brings in**, which is a fact about
        # the day and so cannot be derived on a board that knows only its
        # own fight. Camille's ruling on #666: every two completed
        # encounters. Set before `encounter.start()` arms anything, so a
        # trait that reads it at arming gets the right number.
        session.world.milestones = self.milestones
        leg.entering = self._snapshot(session, leg)

    # -- the turn of a leg -------------------------------------------------

    def _settle(self, session: Session) -> None:
        """Close the current leg once its fight is over. Idempotent.

        Called from `state`, so the page's ordinary poll is what advances the
        day -- there is no moment the client has to report, and a client that
        stops asking leaves the day where it was rather than half-closed.
        """
        if self.finished or not self.session_id or session.id != self.session_id:
            return
        if not session.encounter.finished:
            return
        here = self.legs[self.leg]
        here.rounds = int(getattr(session.world, "round", 0) or 0)
        # `encounter.winner` is a `Team`, and `render.py` reads `.value` off
        # it -- so "pc"/"enemy", not "party"/"monsters". The words below are
        # the **page's** vocabulary: `style.css` styles `leg-won`, `leg-lost`
        # and `leg-abandoned`, and `leg.status` is also printed as prose in
        # the chip, so these are read twice and have to be both.
        won = getattr(session.encounter, "winner", None)
        here.status = {"pc": "won", "enemy": "lost"}.get(
            str(getattr(won, "value", won or "")), "abandoned"
        )
        here.ended = self._snapshot(session, here)
        story.harvest(session.world, self.party)

        # **Rested is read off the sheets, not off the board.** `Party.rest`
        # is the copy that outlives the fight and is the only one that spends
        # surges to heal; the world's own short rest does not, which is why
        # the multi-encounter loop was useless before it existed.
        self.party.rest(extended=BETWEEN_LEGS_EXTENDED)
        here.rested = self._from_sheets(here)
        here.exhausted = any(
            s.hp < s.hp_max and not s.surges for s in here.rested
        )
        short = "an extended rest" if BETWEEN_LEGS_EXTENDED else "a short rest"
        spent = sum(
            max(0, b.surges - a.surges)
            for b, a in zip(here.ended, here.rested, strict=False)
        )
        here.rest_text = (
            f"After {short} the party spent {spent} "
            f"healing surge{'' if spent == 1 else 's'}."
            if spent
            else f"After {short} nobody needed a healing surge."
        )

        self.session_id = ""
        if here.status != "won":
            self.finished = True
            self.outcome = (
                f"The day ends at encounter {self.leg + 1} of {len(self.legs)}."
            )
            return
        if self.leg + 1 >= len(self.legs):
            self.finished = True
            self.outcome = (
                f"The party cleared all {len(self.legs)} encounters."
            )
            return
        self.leg += 1

    # -- reading -----------------------------------------------------------

    @property
    def milestones(self) -> int:
        """Every two completed encounters, Camille's ruling on #666.

        Derived from the legs rather than counted as the day goes, because a
        counter can disagree with the thing it counts -- and this is read by
        `c.milestone()`'s seven rows, which would rather be wrong never than
        wrong sometimes.
        """
        done = sum(1 for leg in self.legs if leg.status not in ("pending", "fighting"))
        return done // 2

    # **What a milestone does not yet do**, so the next reader does not have
    # to measure it: this counts them and the page prints the count, and
    # nothing in the rules kernel reads it. `c.milestone()` is still a marker
    # on seven rows, and a milestone's printed action point is not granted --
    # `Party.rest(extended=True)` sets `action_points = 1`, a short rest sets
    # nothing, and neither is "one more because the party reached a
    # milestone". Both want `World.milestones`, which is #666's engine half
    # and deliberately not in this commit: a field nothing reads is the #583
    # shape, so the field, the reader and the seven rows land together.

    def state(self, session: Session | None = None) -> dto.DayStateDTO:
        if session is not None:
            with self.lock:
                self._settle(session)
        return dto.DayStateDTO(
            id=self.id,
            encounter=self.session_id,
            leg=self.leg,
            scales=list(self.scales),
            legs=[
                dto.DayLegDTO(
                    index=leg.index,
                    scale=leg.scale,
                    status=leg.status,
                    rounds=leg.rounds,
                    entering=list(leg.entering),
                    ended=list(leg.ended),
                    rested=list(leg.rested),
                    rest_text=leg.rest_text,
                    exhausted=leg.exhausted,
                )
                for leg in self.legs
            ],
            awaiting_next=not self.finished and not self.session_id,
            finished=self.finished,
            outcome=self.outcome,
            milestones=self.milestones,
        )

    # -- snapshots ---------------------------------------------------------

    def _snapshot(self, session: Session, leg: _Leg) -> list[dto.DaySheetDTO]:
        """The party as the board has it, and remember the ceilings.

        **The roster is pinned on the first call and reused**, which is the
        whole correctness of this method. Two separate things forced it:

        * `story.harvest` matches sheets to the board by *position*, over
          `[eid for eid, side in world.each(Side) if side.team == Team.PC]`.
          Deriving a different order here -- sorting by entity id, say --
          would be a second order that happens to agree, until the board
          where it did not and the day printed one character's hit points
          under another's name.
        * **That expression grows during the fight.** A familiar is a
          `Team.PC` creature with `Health`, so re-deriving it at the end gave
          five rows against four sheets. Measured, level 3 seed 7, every leg.
          #797 is `harvest`'s own half of that; pinning makes the day
          independent of how it is settled.

        The first call is `Session.create(on_fielded=)`, before the encounter
        starts and before anything has been summoned, so the PC side is
        exactly the party. That is the one moment this list is right.
        """
        from combat_engine.engine.components import Health, Side
        from combat_engine.engine.types import Team

        if not leg.roster:
            leg.roster = [
                eid for eid, side in session.world.each(Side)
                if side.team == Team.PC
                and session.world.get(eid, Health) is not None
            ]
        out: list[dto.DaySheetDTO] = []
        for eid in leg.roster:
            health = session.world.get(eid, Health)
            if health is None:
                continue
            wid = session.wire.id(eid) or str(eid)
            surges = health.surges if health.surges is not None else health.max_surges
            leg.ceilings[wid] = (int(health.max_hp), int(health.max_surges))
            out.append(
                dto.DaySheetDTO(
                    id=wid,
                    label=session.wire.label(eid),
                    hp=int(health.hp),
                    hp_max=int(health.max_hp),
                    surges=int(surges),
                    surges_max=int(health.max_surges),
                )
            )
        return out

    def _from_sheets(self, leg: _Leg) -> list[dto.DaySheetDTO]:
        """The party as the record has it, after the rest.

        Matched to the snapshot taken when the fight ended, by **position** --
        which is what `story.harvest` matches on and for the same reason: a
        `Sheet` carries no entity id, because an id belongs to a world and a
        sheet outlives one.
        """
        order = [s.id for s in leg.ended] or [s.id for s in leg.entering]
        out: list[dto.DaySheetDTO] = []
        for i, sheet in enumerate(self.party.sheets):
            wid = order[i] if i < len(order) else f"c{i}"
            max_hp, max_surges = leg.ceilings.get(wid, (int(sheet.max_hp or 0), 0))
            was = next((s for s in leg.ended if s.id == wid), None)
            out.append(
                dto.DaySheetDTO(
                    id=wid,
                    label=was.label if was else wid,
                    hp=int(sheet.hp if sheet.hp is not None else max_hp),
                    hp_max=int(sheet.max_hp or max_hp),
                    surges=int(
                        sheet.surges if sheet.surges is not None else max_surges
                    ),
                    surges_max=int(max_surges),
                )
            )
        return out


#: Live days, by id. The same shape `session.SESSIONS` uses, and for the same
#: reason: a day outlives a request and the page holds its id.
DAYS: dict[str, Day] = {}
