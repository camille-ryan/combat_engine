"""Offering a power when its printed trigger happens.

4e hangs a great deal on immediate actions -- "when an enemy moves adjacent
to you", "when you are hit by a melee attack", "when an ally within 5 squares
drops". Until this existed, `Power.trigger` was a line of prose that nothing
read, so every one of those rows could be written and none could ever fire:
the interface never offered them, because the interface only offers what a
creature can do *on its own turn*, and by definition none of these happen
then.

The whole mechanism is two observations.

**The bus already has the ordering.** An immediate *interrupt* resolves
before the thing that triggered it and may stop it; an immediate *reaction*
resolves after. `Bus.emit` runs `Window.BEFORE`, then the action itself, then
`Window.AFTER`, and a `BEFORE` listener that cancels stops the action. So the
two action types are the two windows, and nothing new had to be invented to
sequence them.

**The budget already exists.** `Encounter.can_spend` has known since it was
written that an immediate action is once per round and an opportunity action
is once per *other creature's* turn. It simply had no callers for either.

What is left is this file: watch the events that some declared row names,
work out who may respond, and ask them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .components import Powers
from .events import ConditionApplied, Event, RelationSet
from .query import alive, can_act
from .relations import IMPLIES
from .types import ActionType, Condition, Keyword, Window

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


def _always(world: World, me: int, ev: Event) -> bool:
    return True


def _substituted(world: Any, eid: int, ref: str) -> list[int]:
    """1-based variant numbers for every substitution registered on a row.

    The same count `actions._variants` offers the turn menu, read here
    rather than imported: `actions` reaches into this module, and a
    triggered row has to be offered its variants without that becoming a
    cycle.
    """
    known = world.get(eid, Powers)
    if known is None:
        return []
    found = sum(
        len(entries)
        for (on_ref, _what), entries in known.pre_empts.items()
        if on_ref == ref
    )
    return list(range(1, found + 1))


@dataclass(frozen=True)
class Trigger:
    """A printed Trigger line, in a form something can act on.

    `event` is what to watch and `when` is the rest of the sentence. The two
    are separate because the event class is what gets subscribed -- cheap, and
    known at import time -- while the predicate is per-responder and only runs
    for a creature that could actually answer.

    `when` is handed `(world, me, event)`, where `me` is the creature being
    offered the power, not the one that caused the event. "When you are hit"
    and "when an ally is hit" are the same event class and differ only here.

    `text` is the printed line, kept for the power card. It is prose and no
    code reads it; `when` is the authority.
    """

    event: type[Event]
    when: Callable[[World, int, Any], bool] = _always
    text: str = ""
    #: Which side of the event to answer on, when the action's own window is
    #: the wrong one. A free action is a reaction almost always -- "when you
    #: hit, free action: ..." -- so `WINDOW_OF` puts it after. A handful of
    #: printed lines read "**before** the ally makes his first attack roll",
    #: and those cannot be said any other way: the roll, the hit and the
    #: damage all happen inside the `AttackDeclared` emit.
    window: Window | None = None


#: Refs currently resolving, keyed by responder. A reaction that emits the
#: event it watches -- a riposte is an attack, and attacks are what it
#: watches -- would otherwise answer itself forever. The set itself lives in
#: `dsl` now, because every other route into a row needed the same guard and
#: only this one had it; imported where used, since `dsl` imports this back.


WINDOW_OF = {
    ActionType.IMMEDIATE_INTERRUPT: Window.BEFORE,
    ActionType.IMMEDIATE_REACTION: Window.AFTER,
    ActionType.OPPORTUNITY: Window.BEFORE,
    ActionType.FREE: Window.AFTER,
    # "No Action" with a printed Trigger. Not a trait -- a trait is simply
    # true and is armed once at the start -- but a thing that happens when
    # its trigger does and costs nothing. Without an entry here no such row
    # was ever offered to anybody, and four print it.
    ActionType.NONE: Window.AFTER,
}


def _shrugging(ev: Event, eid: int) -> Condition | None:
    """The condition this creature is being asked to answer, if any.

    `Effects.apply` installs a condition and *then* announces it, and that
    ordering is deliberate: announcing first let a listener end the effect
    while its modifiers were still unattached, leaving a penalty on the
    creature forever. The cost is that a row printed as "when you are
    affected by a condition, immediate interrupt: you remove it" is
    offered to a creature that already has the condition -- and dazed and
    stunned both forbid an immediate action, so the two conditions that
    line most exists for were the two it could never answer.

    Waiving exactly the condition being applied, and nothing else, is the
    narrow fix: a creature stunned a round ago still cannot react, which
    is right.

    **A grab, a mark and a domination arrive as a `RelationSet`** and are
    never announced as conditions at all -- #222. So this read them as no
    condition, built no waiver, and every row printed "immediate
    interrupt: you are dominated" was correctly armed and still answered
    nothing: a dominated creature cannot take an immediate action, and
    the one waiver that would have let it was not made. Three rows sat in
    that gap. `IMPLIES` is the same table `Relations._apply_condition`
    uses, so the two stay in step by construction.
    """
    if isinstance(ev, ConditionApplied) and getattr(ev, "target", None) == eid:
        return ev.condition
    if isinstance(ev, RelationSet) and getattr(ev, "target", None) == eid:
        return IMPLIES.get(ev.kind_)
    return None


@dataclass
class Triggers:
    """The dispatcher. One per encounter; owned by it."""

    world: World
    encounter: Encounter
    _subs: list[Any] = field(default_factory=list)

    def arm(self) -> None:
        """Subscribe to every event class any declared row triggers off.

        Done once, from the registry, rather than per creature: the set of
        watched classes is fixed at import time and is small, and a listener
        that walks the creatures is cheaper than a subscription per creature
        per row -- of which a fight would hold several hundred.
        """
        from .dsl import REGISTRY

        watched: dict[type[Event], set[Window]] = {}
        for p in REGISTRY.values():
            window = WINDOW_OF.get(p.action)
            if window is None:
                continue
            for trig in p.triggers:
                watched.setdefault(trig.event, set()).add(trig.window or window)

        for etype, windows in watched.items():
            for window in sorted(windows, key=lambda w: w.name):
                self._subs.append(
                    self.world.bus.on(
                        etype,
                        lambda ev, w=window: self._offer(ev, w),
                        window=window,
                    )
                )

    def disarm(self) -> None:
        for sub in self._subs:
            self.world.bus.off(sub)
        self._subs.clear()

    # -- the offer -----------------------------------------------------------

    def _offer(self, ev: Event, window: Window) -> None:
        """Ask everyone who could answer this event whether they want to.

        Initiative order, so a replay of the same seed offers in the same
        sequence. An interrupt that cancels the event ends the round of
        offers: the thing being responded to is no longer happening.
        """
        for eid in list(self.encounter.order):
            if ev.cancelled:
                return
            # A creature may answer its **own** downfall. A death throe
            # triggers on dropping to 0, and by the time `Dropped` is
            # emitted the thing is no longer alive -- so the liveness check
            # meant no row of that shape could ever be offered to anybody.
            # Three were already written and none of them had ever fired.
            about_itself = getattr(ev, "actor", None) == eid
            if not about_itself and not (
                alive(self.world, eid) and can_act(self.world, eid)
            ):
                continue
            for ref in self._answers(eid, ev, window):
                self._ask(eid, ref, ev)
                if ev.cancelled:
                    return

    def _answers(self, eid: int, ev: Event, window: Window) -> list[str]:
        """Which of this creature's rows this event triggers, in order."""
        from .dsl import _IN_FLIGHT, get, usable

        known = self.world.get(eid, Powers)
        if known is None:
            return []
        dying = getattr(ev, "actor", None) == eid and not alive(self.world, eid)
        out = []
        for ref in known.all:
            p = get(ref)
            if p is None or not p.triggers:
                continue
            if not any(
                (t.window or WINDOW_OF.get(p.action)) is window for t in p.triggers
            ):
                continue
            # Any of them. A row naming several printed triggers answers
            # whichever one actually happened.
            if not any(
                isinstance(ev, t.event)
                and (t.window or WINDOW_OF.get(p.action)) is window
                and t.when(self.world, eid, ev)
                for t in p.triggers
            ):
                continue
            if (eid, ref) in _IN_FLIGHT:
                continue
            if not dying and not self.encounter.can_spend(
                eid, p.action, ignoring=_shrugging(ev, eid)
            ):
                continue
            ok, _why = usable(self.world, eid, p, dying=dying)
            if ok:
                out.append(ref)
        return out

    def _ask(self, eid: int, ref: str, ev: Event) -> None:
        """Offer one power, and use it if it is taken.

        The offer is a real choice -- a printed trigger is permission, not an
        obligation, and several are worth declining to keep the immediate
        action for something better later in the round. With no decider
        installed the first option wins, so taking it comes first: a declared
        reaction that never fired would be the harder bug to see.
        """
        from .dsl import get, use

        p = get(ref)
        if p is None:
            return
        # Each clause substitution registered against this row is another
        # way of taking it, so it joins the offer the dispatcher already
        # makes rather than becoming a second question. A triggered row
        # never reaches the turn menu, so this is the only place its
        # variants can be shown -- without this the registration would be
        # a modifier nothing consults, which is this component's
        # commonest bug and the one four feats here would have had.
        #
        # The printed card stays first, because the note above still
        # holds: with no decider installed the first option wins, and
        # that must be the row as printed rather than whichever feat
        # happened to register.
        options = [ref, *(f"{ref}#{n}" for n in _substituted(self.world, eid, ref)), ""]
        # Comma-joined rather than " or "-joined: an author writing the
        # second fragment naturally ("or knocked prone") would otherwise get
        # "or or" on the card.
        printed = ", ".join(t.text for t in p.triggers if t.text)
        taken = self.world.decide(eid, "trigger", options, printed)
        if not taken or taken.split("#")[0] != ref:
            return
        variant = int(taken.split("#")[1]) if "#" in taken else 0
        dying = getattr(ev, "actor", None) == eid and not alive(self.world, eid)
        if not dying and not self.encounter.spend(
            eid, p.action, ignoring=_shrugging(ev, eid)
        ):
            return

        # `use` adds the pair itself, so nothing is added here -- doing both
        # would have the inner check refuse every triggered row.
        use(self.world, eid, ref, targets=self._at(p, eid, ev), trigger=ev,
            variant=variant)

    def _at(self, p, eid: int, ev: Event) -> list[int] | None:  # noqa: ANN001
        """Who a triggered row is aimed at: whoever the event was about.

        "Make a basic attack against **the enemy**" means the one that just
        swung, and the dispatcher used to pass no targets at all -- so
        `_auto_targets` chose, and a reaction to being attacked shot back at
        whichever enemy happened to be nearest. It shot the wrong one
        whenever two were in reach.

        Only for a row that takes a single creature. A burst picks its own
        targets and a self-buff has none, and neither wants overriding.

        **Which creature depends on the side.** For an enemy row it is
        whoever swung; for an ally row it is whoever it happened *to* --
        "an ally is hit: you take the damage instead" means that ally, and
        this used to handle the enemy case only, so such a row was aimed at
        the nearest ally rather than the hurt one. Silently, and only
        wrong when more than one ally was in range.

        **And when you are the one who swung, it is whoever you hit.** The
        third variant of the same mistake, and the commonest shape in the
        magic item corpus: "when you hit an enemy with this weapon, use
        this power on it" answers your *own* `Hit`, so the attacker is
        you -- the old code found `who == eid`, gave up, and let
        `_auto_targets` pick whichever enemy was nearest. The row applied
        its condition to a creature you had not touched, silently, and
        only when more than one enemy was in reach.
        """
        from .dsl import candidates

        side = p.target.side
        if p.target.everyone or p.target.count != 1:
            return None
        if side == "enemy":
            who = getattr(ev, "attacker", None) or getattr(ev, "actor", None)
            if who == eid:
                who = getattr(ev, "target", None)
        elif side in ("ally", "other_ally", "any", "other"):
            who = getattr(ev, "target", None) or getattr(ev, "actor", None)
        else:
            return None
        if who is None or who == eid:
            return None
        return [who] if who in candidates(self.world, eid, p) else None


# -- the predicates rows actually want --------------------------------------
#
# Written once here rather than as a lambda in every row: "when you are hit"
# is the same sentence in forty places, and forty hand-written versions is
# forty chances to read the wrong field off the event.


def targets_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me


def by_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "attacker", getattr(ev, "source", None)) == me


def by_action_point(world: World, me: int, ev: Event) -> bool:
    """Was the attack this event is about bought with an action point?

    `resolve.attack` rides the flag on all four attack events, the way it
    does `charge`, so "you spend an action point to make an attack and
    miss" is one `both(by_me, by_action_point)` on `Miss`.
    """
    return bool(getattr(ev, "action_point", False))


def about_me(world: World, me: int, ev: Event) -> bool:
    """Reads `ev.actor`, and **only** `ev.actor`.

    Several events name their subject `target` instead -- `ConditionApplied`
    is the common one -- and on those this is silently false, which looks
    exactly like a trigger that never happens. Use `targets_me` there.
    """
    return getattr(ev, "actor", None) == me


def not_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", getattr(ev, "attacker", None)) != me


def ally_within(squares: int) -> Callable[[World, int, Event], bool]:
    """An ally -- not you -- within range of whoever the event is about."""
    from .query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        # The creature the event is *about*. On an attack that is the one
        # swinging, not the one being swung at -- `Hit`, `Miss` and
        # `AttackDeclared` have no `actor`, so falling through to `target`
        # measured the distance to the creature that was missed and called
        # it an ally missing. Silently wrong, and `enemy_within` has had
        # the right fallback all along.
        who = getattr(ev, "actor", None)
        if who is None:
            who = getattr(ev, "attacker", getattr(ev, "target", None))
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def enemy_within(squares: int) -> Callable[[World, int, Event], bool]:
    from .query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", getattr(ev, "attacker", None))
        if who is None or who == me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def _power_of(ev: Event):  # noqa: ANN202
    """Which row caused this, whichever field the event keeps it in.

    An attack event spells it `power`; a damage event spells it `detail`.
    A trigger reading "damages you with a *melee* attack" watches the
    damage and so found nothing to look the reach up from.
    """
    from .dsl import get

    return get(getattr(ev, "power", "") or getattr(ev, "detail", "") or "")


def by_melee(world: World, me: int, ev: Event) -> bool:
    """Was the attack that caused this a melee one?

    "Missed by a *melee* attack" is four rows, and the reach is on the power
    rather than the event. `resolve._is_ranged` already does this lookup for
    cover; this is the other half of the same question.
    """

    p = _power_of(ev)
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in (
        "melee", "close_burst", "close_blast",
    )


def by_ranged(world: World, me: int, ev: Event) -> bool:

    p = _power_of(ev)
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in ("ranged", "area_burst")


def by_opportunity(world: World, me: int, ev: Event) -> bool:
    """Was this an opportunity attack? "When it makes one of those, ..."

    Reads the flag the attack now carries. Before that flag existed the
    question could not be asked at all, and rows printing it were left out.
    """
    return bool(getattr(ev, "opportunity", False))


def not_critical(world: World, me: int, ev: Event) -> bool:
    """The blow was **not** a critical hit. "...but not by a critical hit."

    Reads `Dropped.critical`, which could not be asked at all until #428 gave
    the event the field. Two level-2 rows print the clause and both fired on
    any drop.

    Defaults to `False` for the event rather than raising, so a drop that no
    attack caused -- ongoing damage, a failed death save -- reads as "not a
    critical", which is both true and the printed reading.
    """
    return not getattr(ev, "critical", False)


def by_somebody_adjacent(world: World, me: int, ev: Event) -> bool:
    """Is whoever swung standing next to me? "A creature *adjacent* to it ..."

    An opportunity attack is usually made from an adjacent square, which is
    why a card printing the word reads as saying nothing -- and why
    `m5583a4` dropped the clause and looked finished. **A reach weapon makes
    one from 2 or 3**, and 12 of 117 printed weapons have reach above 1, so
    against one of those the clause is the whole difference.

    Separate from `closed_on_me`, which asks who *moved*. This asks where
    the attacker stands at the moment of the swing, and it is the attacker
    rather than the target because `targets_me` already pins that end.
    """
    from .query import adjacent

    foe = getattr(ev, "attacker", getattr(ev, "source", None))
    return foe is not None and foe != me and adjacent(world, me, foe)


def closed_on_me(world: World, me: int, ev: Event) -> bool:
    """Somebody *else* moved into reach of me.

    "When an enemy moves adjacent to it" -- the creature's own approach does
    not count, and `AdjacencyGained` is emitted mirrored so both ends see
    it. Without asking who moved, a row of this shape fired on its own
    advance as readily as on the enemy's.
    """
    mover = getattr(ev, "mover", 0)
    return mover != 0 and mover != me and getattr(ev, "other", None) in (me, mover)


def left_me(world: World, me: int, ev: Event) -> bool:
    """Somebody *else* moved out of reach of me. `closed_on_me`'s partner.

    "When an enemy moves away from it" -- the creature's own retreat does not
    count, and `AdjacencyLost` is emitted mirrored so both ends see it.

    **This could not be written until `AdjacencyLost` carried `mover`** (#368),
    which is why six rows printing the clause fired on their own withdrawal as
    readily as on the enemy's. Same body as `closed_on_me` because the two
    events are now the same shape, which is the whole point of giving the lost
    half the field the gained half already had: "enters or leaves my reach" is
    one rule and wants one filter.
    """
    mover = getattr(ev, "mover", 0)
    return mover != 0 and mover != me and getattr(ev, "other", None) in (me, mover)


def by_charge(world: World, me: int, ev: Event) -> bool:
    """Was this a charge? "When the m200 charges, ..." """
    return bool(getattr(ev, "charge", False))


def granted_by_me(world: World, me: int, ev: Event) -> bool:
    """"When an ally makes an attack you granted." Whose doing was it?

    Reads the provenance `c.grant_attack`, `c.basic` and `c.charge_at`
    now put on the use. Not `ev.actor`, which names the creature
    swinging -- the whole point of the question is that those are two
    different creatures.
    """
    return getattr(ev, "granted_by", -1) == me


def granted_via(*refs: str) -> Callable[[World, int, Event], bool]:
    """"The melee basic attack granted by <that row>."

    The ref, not the granter: a defender's punishment grants the
    defender its own swing, so "granted by me" is true of half the
    fighter's turn and says nothing. Several refs because one printed
    feature is sometimes two rows.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        return getattr(ev, "granted_via", "") in refs

    return check


def leaves_me_out(world: World, me: int, ev: Event) -> bool:
    """Did this attack miss me out entirely?

    What a defender's mark actually asks. An attack is announced once per
    target, so `ev.target != me` only says *this announcement* was not aimed
    at me -- a burst that caught me still passed that test on every other
    target's row, and both marks punished an enemy for an attack that did
    include them. `among` carries the whole target list of the one power
    use, which is the only thing that can answer it.
    """
    return me not in getattr(ev, "among", (getattr(ev, "target", None),))


def enemy_target_within(squares: int) -> Callable[[World, int, Event], bool]:
    """An enemy of mine, within range, was *on the receiving end* of this.

    "An enemy adjacent to it is hit" reads `ev.target`, where
    `enemy_within` reads the attacker and `ally_within` wants the same
    team. Neither says it, so a row needing it had to write its own.
    """
    from .query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def would_hit_me(world: World, me: int, ev: Event) -> bool:
    """This attack is aimed at me and, as things stand, lands.

    For an interrupt on `AttackRolled`: the die is down and the total is
    known, but the defence is read again once this window closes, so a row
    that raises one can still turn the blow aside. Reading `Hit` instead is
    too late -- by then the comparison has been made and the only thing left
    to change is the damage.
    """
    result = getattr(ev, "result", None)
    return getattr(ev, "target", None) == me and bool(result and result.hit)


def by_keyword(word: Keyword) -> Callable[[World, int, Event], bool]:
    """Was the attack that caused this of a given kind -- cold, fire, radiant?

    Read off the power in the registry, the same way `by_melee` reads its
    reach. "Whenever it takes cold damage" is a shape several monsters have
    and each was writing its own version of this.
    """

    def check(world: World, me: int, ev: Event) -> bool:

        from .dsl import keywords_of

        p = _power_of(ev)
        return p is not None and word in keywords_of(world, me, p)

    return check


def hits_me(world: World, me: int, ev: Event) -> bool:
    """An enemy hit me, at whatever range.

    `enemy_within(n)` forces a distance the printed line does not name, and
    "an enemy hits it" names none.
    """
    from .query import team

    who = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and who is not None
        and team(world, who) is not team(world, me)
    )


def cursed_by_me(world: World, me: int, ev: Event) -> bool:
    """Is whoever this event is about under my curse?

    Three warlock pact boons pay out when a cursed enemy drops, and the
    curse is a relation rather than anything on the event.
    """
    from .types import Relation

    who = getattr(ev, "actor", getattr(ev, "target", None))
    return who is not None and world.relations.holds(Relation.CURSED_BY, me, who)


def my_check(*skills: str) -> Callable[[World, int, Event], bool]:
    """"You make a Stealth check" -- a `SkillCheck` of yours, by name.

    Nine rows open this way and each was writing the same two `getattr`s.
    Naming no skill means any of them.
    """
    wanted = frozenset(s.lower() for s in skills)

    def check(world: World, me: int, ev: Event) -> bool:
        if getattr(ev, "actor", None) != me:
            return False
        return not wanted or getattr(ev, "skill", "") in wanted

    return check


def check_succeeded(world: World, me: int, ev: Event) -> bool:
    """Did the check this event announces beat its DC?

    **After-window only.** `skills.check` totals the modifiers and settles
    `success` inside the resolve callback, which runs once the interrupt
    window has closed -- so in `Window.BEFORE` this is False for every
    check there is, and a row declaring it there never fires.
    """
    return bool(getattr(ev, "success", False))


def check_failed(world: World, me: int, ev: Event) -> bool:
    """The other half of `check_succeeded`, and after-window only for the
    same reason -- before the roll is settled this is true of everything."""
    return not getattr(ev, "success", False)


def both(*checks: Callable[[World, int, Event], bool]) -> Callable[[World, int, Event], bool]:
    """All of these.

    **`parts` is here so `lint.py` can see inside.** `_dead_triggers` looks a
    predicate up by `__name__` to find which field it reads, and a closure is
    called `check` -- so every trigger built with a combinator was **silently
    skipped**, 505 of them across the tree. A level-7 wave wrote `about_me` on
    `Hit` eight times, which reads `ev.actor` on an event that has only
    `attacker` and `target`; lint caught the three bare ones and missed the five
    wrapped in here. One attribute makes all 505 checkable again.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        return all(c(world, me, ev) for c in checks)

    check.parts = checks  # type: ignore[attr-defined]
    return check


def either(*checks: Callable[[World, int, Event], bool]) -> Callable[[World, int, Event], bool]:
    """Any one of these. "You **or** an ally" is a very common opener and
    only `both` existed, so every row saying it wrote its own."""

    def check(world: World, me: int, ev: Event) -> bool:
        return any(c(world, me, ev) for c in checks)

    check.parts = checks  # type: ignore[attr-defined]
    return check


def targets_my_side(world: World, me: int, ev: Event) -> bool:
    """This was aimed at me or at somebody on my side, at any range.

    `ally_within(n)` forces a radius the printed line usually does not name.
    """
    from .query import team

    who = getattr(ev, "target", None)
    return who is not None and team(world, who) is team(world, me)


def hits_my_companion(world: World, me: int, ev: Event) -> bool:
    """"An enemy hits your spirit companion."

    The companion is a target like anything else, so the event names *it*
    and every ready-made predicate asks about the caster -- which made this
    printed line silently false for every row that carries it.
    """
    from .components import Companion
    from .query import team

    victim = getattr(ev, "target", None)
    if victim is None:
        return False
    mine = world.get(victim, Companion)
    if mine is None or mine.owner != me:
        return False
    who = getattr(ev, "attacker", getattr(ev, "source", None))
    return who is not None and team(world, who) is not team(world, me)


def about_my_companion(world: World, me: int, ev: Event) -> bool:
    """Anything at all happening to your companion, whoever caused it."""
    from .components import Companion

    subject = getattr(ev, "target", getattr(ev, "actor", None))
    if subject is None:
        return False
    mine = world.get(subject, Companion)
    return mine is not None and mine.owner == me
