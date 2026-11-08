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


#: The spike's own two numbers. DMG2 chapter 2's second pacing model,
#: paraphrased rather than quoted: one encounter hard enough that the party
#: needs everything it has, with a light build-up before it and an
#: aftermath after. `SPIKE` is deliberately above `FINALE` -- a finale is
#: the hard end of an ordinary day and a spike is the day's whole point.
SPIKE = 1.75
AFTERMATH = 0.75


def spike(count: int) -> list[float]:
    """A day built around one very hard fight. DMG2's second model. #979.

    Standard build-up, the spike, then an aftermath -- so four legs come out
    `1.0, 1.0, 1.75, 0.75`. The spike sits **second from last** rather than
    last, because the page's shape has something after it; a spike with
    nothing following is a finale, which is what `scales` already is.

    **The printed precondition is that the party reaches the spike fresh**,
    and this function cannot enforce it -- a curve is a list of numbers and
    freshness is a fact about the party when it arrives. `Day` reports it
    instead; see `spike_freshness`.

    One fight is the spike alone. Two are the spike and its aftermath: a
    build-up with no spike after it is not a build-up, which is the same
    reasoning `scales` uses for its opener.

    **A spike day totals `count + 0.5` standard encounters, not `count`,
    and that is deliberate.** `scales` and `escalation` both come to
    exactly `count` -- the printed shape of a day -- and this does not,
    because the model's whole point is one fight the party cannot afford.
    Measured: 1.75, 2.5, 3.5, 4.5, 5.5 for one to five legs.
    """
    if count <= 0:
        return []
    if count == 1:
        return [SPIKE]
    if count == 2:
        return [SPIKE, AFTERMATH]
    return [*([1.0] * (count - 2)), SPIKE, AFTERMATH]


def escalation(count: int, level: int | None = None) -> list[float]:
    """A steady ramp to a climax. DMG2's third model. #979.

    Each fight harder than the last, ending on the hardest -- so four legs
    come out `0.75, 1.0, 1.25, 1.5` before the cap below.

    **The climax is bounded by LEVEL, not only by XP, and that bound is the
    thing this model has that the others do not.** The page's reasoning is
    that escalation works by draining the party, so the climax lands on
    characters with nothing left -- and a climax more than a level or two
    above them is a wipe rather than a scare. `FINALE = 1.25` is an XP
    multiplier and carries no such bound, which is `#979`'s point.

    So with a `level`, the last leg is clamped to `climax_cap(level)` -- the
    scale at which the climax costs what a standard encounter two levels up
    costs, which is the printed bound expressed in the only currency a leg
    has. Without a level the ramp is returned unclamped and the caller is
    on its own, which is what `scales` does too.
    """
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    # A ramp centred on standard, so a day of four totals four standard
    # encounters as `scales` does -- the printed shape of a day is the same
    # whichever model paces it.
    step = 0.25
    first = 1.0 - step * ((count - 1) / 2)
    curve = [round(first + step * i, 4) for i in range(count)]
    curve = [max(0.25, x) for x in curve]
    if level is not None:
        cap = climax_cap(level)
        if cap is not None:
            curve[-1] = min(curve[-1], cap)
    return curve


def climax_cap(level: int) -> float | None:
    """The largest scale a climax may carry at this level, or `None`.

    The printed bound on escalation's climax is *a level or two* above the
    party, and a leg carries a scale rather than a level -- so the bound is
    converted through the one function that knows both:
    `story.budget(level + 2) / story.budget(level)`.

    Measured across the band: 1.50 at level 1, 1.33 at 3, 1.50 at 5, 1.43
    at 8, 1.40 at 10.

    **It does not bite on a four-leg day, which is worth knowing before it
    looks broken.** `escalation(4)` climaxes at 1.375 and every cap in band
    is 1.40 or above, so the clamp is inert on the default day and starts
    firing at five legs: `n=5` at level 10 clamps 1.5 to 1.4, and `n=6` and
    `n=7` clamp at every level. A cap that never fires on the common path
    reads exactly like a cap that found nothing, so it is measured here
    rather than assumed.

    **`None` above the monster ceiling, and that case is why this returns an
    option rather than a number.** `story.budget` clamps to `ceiling()`
    because `game.db` stops at level 13, so `budget(15) == budget(13)` and
    the ratio collapses to **1.00** -- which would clamp an escalation
    climax down to a *standard* encounter. That is not the printed bound
    being respected, it is the bound becoming unexpressible, and silently
    returning 1.0 would read as the former. The caller gets `None` and can
    say so.
    """
    from combat_engine import story

    here = story.budget(level)
    above = story.budget(level + 2)
    if not here or above <= here:
        return None
    return above / here


#: The three pacing models, by the name a caller selects. `balanced` is
#: what `scales` has always been -- named here so the default is one of
#: three rather than the one with a name and two without.
CURVES = {"balanced": scales, "spike": spike, "escalation": escalation}


def spike_freshness(legs: list[_Leg], curve: list[float]) -> str:
    """Whether the party reached the spike fresh. `""` when it did. #979.

    The spike model's printed precondition is that the party arrives at the
    big fight with its resources intact, and a day that drained them on the
    build-up has run a different day than the one it asked for. The curve
    cannot check that -- it is a list of numbers -- so this reads the
    snapshot `Day` already takes entering each leg.

    **Reported, never enforced.** Nothing here reshapes the day: a build-up
    that went badly is a fact about the fights, not a mistake in the
    pacing, and silently stiffening or softening a later leg would be this
    layer inventing difficulty. `api/CLAUDE.md`'s rule is that the wire
    does not recompute what the engine decided.

    **The printed precondition names two resources the snapshot does not
    carry, and this is the honest half of it.** The page asks for most of
    their daily powers and an action point apiece; `DaySheetDTO` holds
    `hp`, `hp_max`, `surges` and `surges_max` and neither dailies nor
    action points. So this measures the wear it *can* see -- hit points and
    surges -- and a party that arrives with every daily spent but full hit
    points reads as fresh here. `#979` says both halves are checks on data
    `_Leg` already holds; one of them is not, and the fix is two fields on
    the DTO rather than anything in this function.
    """
    if not curve or SPIKE not in curve:
        return ""
    at = curve.index(SPIKE)
    if at >= len(legs):
        return ""
    entering = legs[at].entering
    if not entering:
        return ""
    worn = [s for s in entering
            if (s.hp_max and s.hp < s.hp_max)
            or (s.surges_max and s.surges < s.surges_max)]
    if not worn:
        return ""
    return (f"{len(worn)} of {len(entering)} reached the spike already worn"
            f" -- the model wants them fresh (hit points and surges only;"
            f" dailies and action points are not in the snapshot)")


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
    #: The slots the dead held, as `Party.bury` returned them, so `rested`
    #: can be matched against the **surviving** wire ids rather than against
    #: all of them. Empty on a leg nobody died in, which is every leg this
    #: field did not exist for.
    #:
    #: `bury` returns slots for exactly this reason and its own docstring
    #: says so -- *"dropping a sheet without dropping the same index from
    #: each silently hands a dead character's name [...] to whoever was
    #: behind them"*. This caller discarded the return value and the comment
    #: beside it argued that was safe, *"no `Campaign` state to keep in step
    #: here because a day has no personas or formation"*. A day has no
    #: personas; it does have this order.
    buried: list[int] = field(default_factory=list)
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
    #: Which of DMG2's three pacing models shaped `scales`, by its name in
    #: `CURVES` -- or `""` when the caller passed its own numbers, because
    #: an explicit curve belongs to no model and claiming one would be a
    #: guess. Recorded rather than derived: three of the four-leg curves
    #: are distinguishable by their numbers but a caller's own list can
    #: coincide with one, and "which model did the user ask for" is not the
    #: same question as "which model does this look like". #979.
    curve: str = ""
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
        curve: str = "balanced",
        fights: int = 4,
    ) -> Day:
        """Deal the party and set out the legs. No fight is built yet.

        `want` is the page's four boxes. Empty or absent falls back to the
        named `curve` -- `balanced` by default, which is `scales(4)` and the
        same curve those boxes ship pre-filled with, so the default lives in
        two places on purpose and they are asserted equal rather than one
        being derived from the other across the wire.

        **`want` wins over `curve`, deliberately.** The boxes are the user
        typing numbers and a model is a starting point; a named model that
        overrode an explicit list would throw away the more specific
        instruction. A day dealt from `want` records `curve=""` rather than
        guessing which model its numbers resemble. #979.

        `escalation` is handed the party's `level`, because its climax is
        bounded by level and the other two carry no such bound -- see
        `climax_cap`.
        """
        import uuid

        if curve not in CURVES:
            raise ValueError(
                f"curve={curve!r}: not one of {', '.join(sorted(CURVES))}")
        named = CURVES[curve]
        # Only `escalation` takes a level, so this is not a uniform call --
        # passing one to the other two would be a parameter they ignore,
        # which reads as a curve that honours a bound it does not have.
        shaped = (named(fights, level) if named is escalation
                  else named(fights))
        # **`picked`, not `curve`.** Reusing the parameter's name for the
        # list shadows the model's name, and the `Day` field below needs
        # both -- the numbers and which model asked for them.
        picked = [float(x) for x in (want or [])] or shaped
        model = "" if want else curve
        if not picked:
            raise ValueError("a day needs at least one fight")
        if any(x <= 0 for x in picked):
            raise ValueError("a fight's budget multiplier must be positive")
        party = story.Party.of(pcs or list(story.PARTY), level, seed=seed)
        return cls(
            id=uuid.uuid4().hex[:12],
            seed=seed,
            level=level,
            scaling=scaling,
            pcs=list(pcs) if pcs else None,
            scales=picked,
            curve=model,
            party=party,
            legs=[_Leg(index=i, scale=s) for i, s in enumerate(picked)],
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
        # **The dead leave the party, before the rest and not after.** An
        # extended rest sets `hp = None`, which erases the number that says
        # somebody died, and a short rest's `heal` skips them and leaves a
        # sheet at -26 for `_wear` to clamp to 0 -- which is #923, and which
        # `api_smoke`'s own carry check is what caught. Camille's ruling,
        # 2026-10-30: a character past the death floor is out.
        #
        # The seam is crossed deliberately: the fix is `story`'s, but a
        # `Day` holds a `Party` and no `Campaign`, so this is the only place
        # arcade mode can make the call.
        #
        # **The slots are kept, and discarding them was a bug.** This line
        # read `self.party.bury()` and the comment here argued that was
        # enough -- "no `Campaign` state to keep in step here because a day
        # has no personas or formation". True of personas and false of the
        # thing that matters: `_leg.pinned` and `leg.ended` are wire ids
        # **parallel to the sheets by index**, so a sheet removed from the
        # middle shifts every sheet behind it against them.
        #
        # Measured: the Rogue dies in slot 2 of 4 and `rested` published the
        # Wizard's hit points under the Rogue's id and label, with every
        # count agreeing. It was invisible until now because the only death
        # the pinned day had ever produced was in the **last** slot, where
        # dropping the last sheet and dropping the last id coincide. #1101
        # exercised exactly that case.
        here.buried = self.party.bury()

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

        **Minus the slots the dead held**, because `bury` has already run by
        the time this is called and `self.party.sheets` is the shorter list.
        Matching by position against the full order hands a dead
        character's id and label to whoever was behind them -- see
        `leg.buried`.
        """
        order = [s.id for s in leg.ended] or [s.id for s in leg.entering]
        order = [w for i, w in enumerate(order) if i not in set(leg.buried)]
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
