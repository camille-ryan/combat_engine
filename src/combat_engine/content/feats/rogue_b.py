"""Rogue feats, the second batch.

`rogue.py` holds the first, and the split it describes runs through this
one twice as hard. Most of these ride on the class's extra damage or on
a weapon the catalogue does not carry, and those are two different gaps
that look alike from the outside.

**The extra damage announces itself after all.** It used to be written
here that it did not: `cf:rogue-scoundrel-f4` pays out inside a closure
in `content/features/strikers.py`, so nothing could see the payout. But
that closure pays through `c.damage(..., detail=label)`, and
`DamageRolled` carries `source`, `target`, `amount` and `detail` -- and
is a `Decision`, so a `Window.BEFORE` listener may change the number.
That is the announcement, and five rows here were waiting on a verb for
something they could already read. What is still shut is narrower and
worth keeping apart:

* the **latch**, a dict inside `extra_damage` keyed on the turn. It
  cannot be reset, so "this use does not count" is written as one spare
  payout handed out for later rather than as a use given back --
  f818 and f2426 both do that, and neither can ever pay twice because
  each spends its spare only once the class has already paid this turn.
* the **condition**, the `applies=` callable that closure closes over.
  Widening it from outside would mean a second latch beside the first
  and two payouts in a turn, which is why f2076 still waits.
* the **dice**, which are rolled inside `c.damage` and gone. `c.bonus`
  reaches the total -- `c.bonus("cf:rogue-scoundrel-f4 damage", n)` is
  what `extra_damage` adds on top, and `dice=` puts a whole die there --
  but no modifier takes a die back out or rerolls one that came up low.

**The weapon gate is a ref, not a group, wherever the group is wider
than the card.** `chargen` carries ten weapons. A card reading "while
wielding a rapier" cannot be written as the `light blade` group, because
the dagger every rogue starts with is a light blade and is not a rapier
-- so the benefit would be paid in a fight the card never paid it in.
Those rows ask `Weapon.ref` instead, which is exact, and is inert on a
board until `chargen` grows a rapier. Where the group genuinely covers
the printed list -- bows and crossbows -- the group is used, which is
the reading `strikers._SNEAK_GROUPS` already settled on.

The style family is here too, and behaves as it does in `fighter_b.py`
and `ranger_b.py`: the `Associated Powers:` list resolves to refs, so
the clause is one `ev.power in ...` read, and the second benefit is
`c.as_basic`, filed under the window the card names.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Gear,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    ActionPointSpent,
    AttackDeclared,
    DamageApplied,
    DamageRolled,
    PowerResolved,
)
from combat_engine.engine.query import allies, has_combat_advantage

from .styles import hit_with_one_of, used_one_of

#: The narrower half of the extra damage: *when* it applies is the
#: `applies=` callable closed over inside `strikers.extra_damage`, and a
#: feat that widens it has nothing to widen -- see the module docstring
#: for why a second latch beside the first is not the answer.
APPLIES = ("c.extra_damage(applies=)",)
#: One weapon group standing in for another, for named rows only.
COUNTS_AS = ("c.counts_as(group=)",)
#: Nothing adds to the distance somebody else's shift covers.
EXTEND_SHIFT = ("c.extend_shift()",)

#: The class feature whose payout half this file keeps reaching for.
_SNEAK = "cf:rogue-scoundrel-f4"

#: The two conditions f2369 narrows its save penalty to. Compared by
#: value, as `ranger_b.f2367` does -- the saving throw's context hands
#: over `Condition` members and the card names words.
_STUNNING = ("dazed", "stunned")
#: The four f813 narrows its own to, read the same way.
_SOFTENING = ("blinded", "immobilized", "slowed", "weakened")

#: The printed weapons that `chargen` has no entry for. Asking by ref
#: keeps the row exact; see the module docstring for why the group is
#: not good enough.
_RAPIER = ("w3620",)
_SWORDS = ("w3610", "w3611", "w3620")
_CLUBS = ("w3593", "w3596")


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster holding one of these weapon groups, in either hand?

    The same helper `ranger_b.py` defines. Repeated rather than imported
    for the reason the class files are separate at all.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    ranged = [gear.ranged] if gear.ranged is not None else []
    return any(w.group in groups for w in (*gear.melee, *ranged))


def _holding_ref(c: Cast, *refs: str) -> bool:
    """The same question asked of the weapon itself rather than its group."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.ref in refs for w in gear.held)


def _martial(p, *, usage=None) -> bool:  # noqa: ANN001
    if p is None or Keyword.MARTIAL not in p.keywords:
        return False
    return usage is None or p.usage in usage


def _my_martial_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power))


def _my_martial_encounter_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power), usage=(ENCOUNTER,))


def _my_rogue_encounter_miss(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "rogue"
        and p.usage is ENCOUNTER
    )


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _at_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me


def _was_opportunity(ev: Any) -> bool:
    """`getattr`, because `resolve.attack` hangs `opportunity` on the
    outcome as a plain attribute rather than declaring it a field.

    Asked in the body rather than in the predicate for the same reason
    `fighter_b.f1971` asks it there: a declared trigger is matched
    against the event class and its fields, and a gate on an attribute
    the dataclass does not carry belongs on the other side of the offer.
    """
    return bool(getattr(ev, "opportunity", False))


def _slip_away(c: Cast, squares: int) -> None:
    """"Shift N squares and make a Stealth check to become hidden."

    The DC is the best passive Perception in the room, which is the same
    number `cf:rogue-tactic-stealth` rolls against -- written the same
    way here so the two cannot disagree about what going unseen costs.
    """
    c.shift(squares)
    watching = [c.passive("perception", of=foe) for foe in c.enemies()]
    if c.check("stealth", max(watching) if watching else 10):
        c.hide()


# -- reading the class's extra damage from outside --------------------------


def _window(c: Cast) -> object:
    """The slot `strikers.extra_damage` latches the rogue's payout in.

    Written the same way as the closure's own `window()`, because a row
    asking "has it paid this turn?" and the latch deciding it must not
    be able to disagree. The rogue's card says *turn*, so the initiative
    slot is part of the answer and the round alone is not.
    """
    fight = c.world.encounter
    if fight is None:
        return c.world.round
    return (c.world.round, fight.index)


def _round_of(slot: object) -> int:
    return slot[0] if isinstance(slot, tuple) else int(slot)  # type: ignore[index]


def _watch_payout(c: Cast) -> Callable[[], object]:
    """Remember the slot the class's extra damage was last paid in.

    The payout goes out through `c.damage(..., detail=label)`, so
    `DamageRolled.detail` names it. Returns a reader rather than a
    number because every caller asks later, from inside a trigger.
    """
    seen: list[object] = []

    def note(ev: DamageRolled) -> None:
        if ev.source == c.me and ev.detail == _SNEAK:
            seen.append(_window(c))

    c.watch(
        DamageRolled, note, on=c.me, until=When.ENCOUNTER,
        label=f"{c.ref} watched the payout",
    )
    return lambda: seen[-1] if seen else None


def _pay(c: Cast, who: int) -> int:
    """Pay the extra damage once, dice and modifier both.

    `c.sneak_damage` is the dice and `c.total` is what `extra_damage`
    adds on top, so a build feature that raises one raises this too.
    """
    return c.damage(
        c.sneak_damage(), c.total(f"{_SNEAK} damage"), on=who, detail=_SNEAK
    )


def _spare_use(c: Cast, paid: Callable[[], object]) -> None:
    """Hand out one extra payout, spent on a later hit this turn.

    The latch itself cannot be reset -- it is a dict inside a closure --
    so "that use does not count" is written as a second payout rather
    than as a use given back. **It is spent only once the class has
    already paid in this slot**, which is what makes it safe: if this
    watcher runs ahead of the feature's on the same `Hit` it simply
    declines and catches the next one, and there is no order of the two
    in which the rogue is paid twice for one use.
    """

    def spend(ev: Hit) -> None:
        if ev.attacker != c.me or paid() != _window(c):
            return
        if has_combat_advantage(c.world, c.me, ev.target):
            _pay(c, ev.target)

    c.watch(
        Hit, spend, on=c.me, until=When.EOT, once=True,
        label=f"{c.ref} spare payout",
    )


# -- the rows that play -----------------------------------------------------


@power("f2075", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2075(c: Cast) -> None:
    """Charisma on two skills, as a feat bonus after the errata.

    Not `out_of_combat`: `skills.modifier` reads a `skill:<name>`
    modifier like any other, so this is an ordinary standing bonus and
    an Athletics check inside a fight sees it.
    """
    for skill in ("acrobatics", "athletics"):
        c.bonus(f"skill:{skill}", c.cha_mod, on=c.me, until=When.ENCOUNTER,
                kind="feat")


@power("f820", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.extend_move()",),
       trigger="an opportunity attack hits you while you are moving",
       on=Trigger(Hit, _at_me, "you are hit"))
def f820(c: Cast) -> None:
    """Being caught on the way out makes you faster.

    Untyped and `stacks=True` by default, which is the printed
    "cumulative if you are hit multiple times" -- and `AT_WILL`, because
    a triggered row declared `ENCOUNTER` fires once a fight and
    "cumulative" is the card saying outright that it does not. That was
    the bug: the second hit laid nothing. `When.EOT` rather than the
    printed "for that move": the move in flight has already had its
    budget measured, so what is dropped is the retroactive half and what
    plays is the rest of the turn.
    """
    if _was_opportunity(c.trigger):
        c.bonus("speed", 1, on=c.me, until=When.EOT)


@power("f2077", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a rogue encounter attack",
       on=Trigger(Miss, _my_rogue_encounter_miss, "you miss"))
def f2077(c: Cast) -> None:
    """Consolation damage on a miss.

    `c.flat` rather than `c.damage`, because the printed number is a
    modifier and not dice -- and a flat number is not maxed by anything.
    """
    if _holding_ref(c, *_RAPIER):
        c.flat(c.cha_mod, on=c.trigger.target)


@power("f2380", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit")
def f2380(c: Cast) -> None:
    """A crit leaves the target open; `p4477` stands in for the melee
    basic on an opportunity attack. Only `p4477` of the printed pair is
    heroic, so the list is one long here."""
    if not _holding_ref(c, *_SWORDS):
        return
    c.as_basic("p4477", window="opportunity")

    def on_crit(ev: Any) -> None:
        if _i_crit(c.world, c.me, ev) and _holding_ref(c, *_SWORDS):
            c.grants_advantage(on=ev.target, until=When.EONT)

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f2451", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack, or one misses you",
       on=(Trigger(Hit, _i_hit, "you hit"),
           Trigger(Miss, _at_me, "an attack misses you")))
def f2451(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- and the creature
    that grants the advantage is on the other end of the swing in each
    case, which is what the branch picks out."""
    ev = c.trigger
    if not _was_opportunity(ev):
        return
    c.grants_advantage(
        on=ev.target if isinstance(ev, Hit) else ev.attacker, until=When.EONT
    )


@power("f2350", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial encounter power")
def f2350(c: Cast) -> None:
    """"Any ally, while adjacent to you", so the adjacency is asked per
    attack: the ally walks in and out of it while the bonus stands."""
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not any(
        w.group in ("axe", "hammer", "mace") and "versatile" in w.properties
        for w in gear.melee
    ):
        return
    c.as_basic("p4488", "p2284", window="opportunity")

    def on_hit(ev: Any) -> None:
        if not _my_martial_encounter_hit(c.world, me, ev):
            return
        for friend in [a for a in allies(c.world, me) if a != me]:
            c.bonus(
                AC, 2, on=friend, until=When.EONT, kind="feat",
                when=lambda ctx, f=friend: c.adjacent_to(f, me),
            )

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2369", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial power, or use an associated power",
       on=(Trigger(Hit, _my_martial_hit, "you hit with a martial power"),
           Trigger(PowerUsed, used_one_of("p10769", "p1387"),
                   "you attack with an associated power")))
def f2369(c: Cast) -> None:
    """Both printed benefits, and they answer different events.

    The save penalty is narrowed by the saving throw's own context,
    which carries the conditions the effect holds -- the same reading
    `ranger_b.f2367` uses.

    The rattling half is laid on `PowerUsed`, which fires *before* the
    body: `c.rattling` is a modifier `c.damage` reads beside the header,
    so it has to be standing by the time the blow lands. `When.EOT`
    rather than the instant, because there is no duration shorter than
    the turn and the row is the only attack being made inside it.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(
        w.group in ("hammer", "flail", "mace") and not w.two_handed
        for w in gear.melee
    ):
        return
    if isinstance(c.trigger, PowerUsed):
        c.rattling(on=c.me, until=When.EOT)
        return
    c.penalty(
        "save", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: any(
            str(x.value) in _STUNNING for x in ctx.get("conditions", ())
        ),
    )


@power("f2388", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial power, or use an associated power",
       on=(Trigger(Hit, _my_martial_hit, "you hit with a martial power"),
           Trigger(PowerUsed, used_one_of("p982"),
                   "you attack with an associated power")))
def f2388(c: Cast) -> None:
    """A Perception penalty, and a vanishing act before the shot.

    `skill:perception` is a modifier key `skills.modifier` reads, so the
    first benefit is an ordinary penalty rather than a narrative one --
    and it is what a passive Perception is measured from, which is the
    number the second benefit rolls against.

    "Before the attack" is only sayable on `PowerUsed`, which is
    announced above the body.
    """
    if not _holding(c, "bow", "crossbow"):
        return
    if isinstance(c.trigger, PowerUsed):
        _slip_away(c, 2)
        return
    c.penalty("skill:perception", 2, on=c.trigger.target, until=When.EONT)


@power("f2362", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=EXTEND_SHIFT,
       trigger="you attack with an associated power",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and ev.power == "p4488"
       ), "you attack with an associated power"))
def f2362(c: Cast) -> None:
    """"**After** the attack", so `PowerResolved` and not `PowerUsed`.

    The two are the same row's bookends and picking the wrong one puts
    the shift on the far side of the swing from where the card prints
    it. `AT_WILL`, because the card prints no limit and an `ENCOUNTER`
    triggered row fires once a fight. The other benefit -- every shift
    this turn is a square longer -- is dropped: nothing reaches into the
    distance another row's shift covers, which `ranger_b.f2361` named
    first.
    """
    if _holding(c, "light blade"):
        _slip_away(c, 2)


@power("f2338", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.as_ranged(ref)", "c.counts_as(group=)"),
       trigger="you attack with a bow or a crossbow",
       on=Trigger(AttackDeclared, lambda w, me, ev: ev.attacker == me,
                  "you attack", window=Window.BEFORE))
def f2338(c: Cast) -> None:
    """No reprisal from the creature you are shooting at.

    Declared `BEFORE`, for the reason `ranger_b.f2337` is: the
    provocation happens as the shot is taken, and an `AFTER` window
    hands over the exemption once the reprisal has been made.
    `from_=` names the one creature the card exempts, which is not the
    same as not provoking at all. `AT_WILL` for the reason f2362 is.

    The second benefit is two clauses and both are gaps: turning a named
    melee row into a ranged one for this use, and letting a crossbow
    stand in for the light blade it asks for.
    """
    if _holding(c, "bow", "crossbow"):
        c.no_provoke(from_=c.trigger.target, on=c.me, until=When.EOT)


@power("f2354", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignore_cover(reduce=)",))
def f2354(c: Cast) -> None:
    """Cover and concealment do not count on the two shots this names.

    The associated list used to be missing from the spec -- an errata
    block sat between it and the benefit -- and it is there now, so the
    row is a gated `c.ignore_cover` and nothing more.

    `partial=True` rather than the full waiver, which is the conservative
    half of the printed sentence: the ordinary -2 goes and superior cover
    stands. Turning the -5 into a -2 is not sayable, because
    `query.cover_waived` is a **threshold** -- `resolve.attack` zeroes the
    penalty when the waiver reaches it and otherwise leaves it whole --
    so the only numbers available are "all of it" and "none of it", and
    the full waiver would beat superior cover outright.

    The marker names the argument that is missing rather than the reader
    that is present: `query.cover_waived` exists, which made the marker
    read as arrived the moment anybody looked at it. What no call can
    say is *reduce this penalty by two*.
    """
    if not _holding(c, "crossbow", "bow", "sling"):
        return
    c.ignore_cover(
        partial=True, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") in ("p10766", "p10755") and bool(ctx.get("ranged"))
        ),
    )


@power("f1775", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2475",
       on=Trigger(PowerUsed, used_one_of("p2475"), "you use p2475"))
def f1775(c: Cast) -> None:
    """Combat advantage against whoever provoked `p2475`.

    `PowerUsed.trigger` is the event the row was used in answer to, and
    `p2475` answers a `Hit` on itself -- so "the triggering attacker" is
    one read off it. `ev.targets` is not that creature: `p2475` is an
    interrupt and does not target the one that swung.
    """
    attacker = getattr(c.trigger.trigger, "attacker", None)
    if attacker is not None:
        c.grants_advantage(on=attacker, until=When.EONT)


@power("f810", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerUsed, used_one_of("p1628"), "you use p1628"))
def f810(c: Cast) -> None:
    """Deepens the rattling penalty against `p1628`'s victim, -2 to -4.

    `Cast._rattle` lays a flat -2 and nothing raises it, but penalties
    bucket by the **label** of the row that laid them and only two from
    one source refuse to add -- so a second -2 of this row's own comes
    to the printed -4. Laid on `DamageApplied`, which is emitted from
    inside `c.damage` just before `_rattle` runs, so it lands exactly
    when the rattle does and never on a blow that dealt nothing.

    `p1628` is `NO_TARGET` and aims off its own trigger, so the victim
    is read there rather than from `ev.targets`, which is empty.

    The narrower "rattling melee" modifier is not asked: `DamageApplied`
    does not say whether the blow was a melee one, and the two rows that
    grant that modifier are not in reach of this feat's prerequisite.
    """
    me = c.me
    victim = getattr(c.trigger.trigger, "attacker", None)
    if victim is None:
        return

    def deepen(blow: DamageApplied) -> None:
        if blow.source != me or blow.target != victim:
            return
        p = get(blow.detail)
        rattles = (p is not None and Keyword.RATTLING in p.keywords) or bool(
            c.total("rattling")
        )
        if rattles:
            c.penalty("attack", 2, on=victim, until=When.EONT)

    c.watch(DamageApplied, deepen, on=me, until=When.EONT)


@power("f2449", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p6189",
       on=Trigger(Hit, hit_with_one_of("p6189"), "you hit with it"))
def f2449(c: Cast) -> None:
    """"The enemy you hit" is the blow rather than the declaration, so
    this hangs on `Hit` and not on `PowerUsed` -- the racial power can
    miss."""
    c.grants_advantage(on=c.trigger.target, until=When.EONT)


@power("f819", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reroll an attack with p1450 and the second roll misses",
       on=Trigger(PowerResolved, used_one_of("p1450"), "you use p1450"))
def f819(c: Cast) -> None:
    """Refunds `p1450` when the reroll it bought misses anyway.

    Nothing announces that a roll *was* a reroll, but nothing has to:
    `p1450` is an interrupt on `AttackRolled` whose whole body is the
    reroll, so the attack that event names is the rerolled one by
    construction. `PowerResolved.trigger` hands it over, and the
    `advantage` field on it is "an enemy granting you combat advantage"
    asked at the moment of the roll rather than afterwards.

    The outcome is recomputed after the interrupt window, so the miss is
    waited for rather than read: one `Miss` against the same creature,
    this turn.
    """
    rolled = c.trigger.trigger
    if rolled is None or not getattr(rolled, "advantage", False):
        return
    victim = rolled.target

    def refund(ev: Miss) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.restore_use("p1450")

    c.watch(Miss, refund, on=c.me, until=When.EOT, once=True)


@power("f829", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f829(c: Cast) -> None:
    """`p1766` burns through fire resistance and immunity while you have
    combat advantage against its target.

    `advantage` is a key the damage context carries, asked of the board
    at damage time -- which is right for a standing grant and blind to a
    one-shot that the attack roll already spent. The narrower reading
    would need the rolled result threaded down to here."""
    c.ignore_resistance(
        None, DamageType.FIRE, on=c.me, until=When.ENCOUNTER, immunity=True,
        when=lambda ctx: ctx.get("power") == "p1766"
        and bool(ctx.get("advantage")),
    )


# -- the extra damage, read off `DamageRolled` ------------------------------


@power("f809", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f809(c: Cast) -> None:
    """Trades combat advantage to every enemy for a bigger payout.

    The offer is made at the one moment the card makes it: the payout is
    announced as a `DamageRolled` carrying the feature's label, and that
    event is a `Decision`, so a `Window.BEFORE` listener changes the
    number that is about to land. `c.bonus` on the feature's own
    modifier key would have added the +2 to every payout instead, which
    is not a choice and would charge the price once for the whole fight.
    """
    me = c.me

    def offer(ev: DamageRolled) -> None:
        if ev.source != me or ev.detail != _SNEAK:
            return
        if not c.may("add 2 damage and grant combat advantage to every enemy"):
            return
        ev.amount += 2
        for foe in c.enemies():
            c.grants_advantage(on=me, to=foe, until=When.EONT)

    c.watch(
        DamageRolled, offer, on=me, until=When.ENCOUNTER, window=Window.BEFORE
    )


@power("f813", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f813(c: Cast) -> None:
    """A save penalty on the four conditions, after a club or mace payout.

    Both halves are readable now. "You dealt the extra damage" is the
    `DamageRolled` the feature pays it with, and "against any of those
    conditions" is the saving throw's own context, which carries the
    conditions the effect holds -- the reading f2369 uses.

    What is approximated is "that causes the target to become": the
    conditions a power applies land in its body *after* the `Hit` the
    payout rides on, so there is nothing to read at this moment. The
    penalty is therefore laid on the target and narrowed to those four
    words, which is wider than the card by any of them the target picks
    up later in the fight from somebody else.
    """
    me = c.me

    def on_payout(ev: DamageRolled) -> None:
        if ev.source != me or ev.detail != _SNEAK:
            return
        if not _holding_ref(c, *_CLUBS):
            return
        c.penalty(
            "save", 2, on=ev.target, until=When.ENCOUNTER,
            when=lambda ctx: any(
                str(x.value) in _SOFTENING for x in ctx.get("conditions", ())
            ),
        )

    c.watch(DamageRolled, on_payout, on=me, until=When.ENCOUNTER)


@power("f818", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f818(c: Cast) -> None:
    """A second helping of the extra damage after an action point.

    `ActionPointSpent` is the trigger and `DamageRolled` answers "have
    you already dealt it this round". The latch cannot be reset, so the
    second helping is a spare payout spent on a later hit this turn --
    see `_spare_use` for why that can never come to two payouts where
    the card grants one.
    """
    paid = _watch_payout(c)

    def spend(ev: ActionPointSpent) -> None:
        last = paid()
        if ev.actor == c.me and last is not None and _round_of(last) == c.world.round:
            _spare_use(c, paid)

    c.watch(ActionPointSpent, spend, on=c.me, until=When.ENCOUNTER)


@power("f2426", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2426(c: Cast) -> None:
    """The racial power's target pays, and the use does not count.

    The first printed clause is already true of a rogue with the
    feature: its condition -- combat advantage against the target -- is
    exactly the feature's own, so a hit with `p1766` pays whenever the
    latch is free. The clause that is this feat's is the second one, and
    it is written as one spare payout for later rather than as a use
    handed back, because the latch is a dict inside a closure.

    So the total over a turn is the printed total; which attack carries
    the second helping is a square the engine cannot place it on.
    """
    paid = _watch_payout(c)

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != "p1766":
            return
        if has_combat_advantage(c.world, c.me, ev.target):
            _spare_use(c, paid)

    c.watch(Hit, on_hit, on=c.me, until=When.ENCOUNTER)


@power("f952", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_damage()",))
def f952(c: Cast) -> None:
    """Forgoes one die of the extra damage to lay an attack penalty. The
    payout is announced -- `DamageRolled` carries the label and the
    amount, and a `BEFORE` listener may change it -- but the dice are
    already summed into that number, so there is no die to decline.
    Subtracting a fresh roll instead would be a different distribution
    dressed up as the printed one."""


@power("f1661", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_ones()",))
def f1661(c: Cast) -> None:
    """Rerolls the low dice of the extra damage when `p8278`'s necrotic
    rides along. The payout is announced and the racial power is a ref,
    so neither the naming nor the moment is the gap; `DamageRolled`
    carries one total and the individual faces are gone by the time
    anything sees it."""


@power("f2076", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=APPLIES)
def f2076(c: Cast) -> None:
    """Pays the extra damage without combat advantage when you are the
    only creature beside the target. That is the `applies=` callable
    `strikers.extra_damage` closes over, and widening it from out here
    means a second watcher with a latch of its own -- which pays twice
    in any turn that has one hit of each kind in it. The rapier half is
    writable, see f2077, and is not what holds this up."""


# -- one weapon group standing in for another -------------------------------


def _counts_as(ref: str, what: str, *, wants: tuple[str, ...] = COUNTS_AS) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} `c.as_implement` rewrites a weapon's group outright; the "
        "general form -- count as a light blade *for these rows only* -- "
        "has no verb. `rogue.py`'s f799 named it first."
    )


# **These two have a body and the helper above cannot give them one.** Both
# print the swap *and* its price -- a die off the class's extra damage while the
# stand-in weapon is in hand -- and the price is writable now that
# `strikers.extra_damage` asks `c.dice_for` for its die. So they are written out
# rather than passed through `_counts_as`, which exists for the rows whose whole
# benefit is the swap.


def _price(c: Cast, groups: tuple[str, ...]) -> None:
    """A die off the class's extra damage while one of those is in hand.

    The feature prints 2d6 at every level this build imports, so one die fewer
    is 1d6 outright. The gate asks the board what is held at the moment of the
    hit rather than at arming, because a rogue draws and stows mid-fight and a
    flag set when the trait armed would still be saying "mace" afterwards.
    """
    c.change_dice(
        "cf:rogue-scoundrel-f4", "1d6", on=c.me,
        when=lambda ctx: any(c.wielding(g) for g in groups),
    )


@power("f821", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.counts_as(group=)",))
def f821(c: Cast) -> None:
    """A mace where the rows ask for a light blade, at the cost of a die of
    the extra damage.

    The price is written. The swap is the dropped clause: `c.as_implement`
    rewrites a weapon's group outright, and the general form -- count as a
    light blade *for these rows only* -- has no verb. `rogue.py`'s f799 named
    it first.

    Inert until that lands, and correct rather than guessed: the class feature
    refuses a mace, so there is no extra damage to charge a die against yet.
    The clause is right the day the swap works."""
    _price(c, ("mace",))


@power("f825", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.counts_as(group=)",))
def f825(c: Cast) -> None:
    """An axe, a hammer or a pick where the rows ask for a light blade, at the
    cost of a die of the extra damage.

    f821 with three groups instead of one; see it for why the price is
    written and the swap is not."""
    _price(c, ("axe", "hammer", "pick"))


_counts_as("f2078", """A one-handed heavy blade where the rows ask for a
           light blade, the extra damage included. The proficiency half
           is a column and not a body.""")
_counts_as("f2437", """A hammer where the rows ask for a light blade.""")
_counts_as("f2471", """A bow where the rows ask for a crossbow. The extra
           damage already takes a bow -- `strikers._SNEAK_GROUPS` has
           it -- so what is left is the rogue powers.""")
_counts_as("f2895", """A shortbow where the rows ask for a crossbow. The
           proficiency half is a column.""")


# -- the rest of the gaps, each named exactly -------------------------------


@power("f826", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Weapon.off_hand_anyway", "c.reload()"))
def f826(c: Cast) -> None:
    """A hand crossbow held in the off hand and reloaded one-handed.
    `Gear.off` is the second *melee* weapon by construction, so there is
    nowhere to put a shooter, and loading is not modelled at all -- which
    makes "have a loaded one in your off hand" unaskable and the free
    shot on a crit with it unreachable."""


@power("f2073", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.shield_bonus()",))
def f2073(c: Cast) -> None:
    """Raises the light shield's bonus by one. `Gear.shield` is a bool
    and the light-or-heavy number was folded into the defence totals at
    spawn, so there is neither a number to raise nor a way to tell which
    shield is being carried. The fighter's f1741 named it first."""


@power("f2074", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.shield_bonus()", "c.on_power_bonus()"))
def f2074(c: Cast) -> None:
    """Adds one to a power bonus to defences while a light shield is
    carried. Two gaps: which shield it is, and that a bonus being laid
    announces nothing a row can answer -- `Mods` records the number and
    its kind, not the act of granting it."""


@power("f2405", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.counts_as(property=)", "Weapon.proficiency"))
def f2405(c: Cast) -> None:
    """The sling exists now; what does not is any way to rewrite the
    weapon a character is holding. Both clauses are that -- a better
    proficiency bonus and the high-crit property -- and `Weapon` is read
    off the item rather than off the wielder."""


@power("f2429", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_distance(ref, n)",))
def f2429(c: Cast) -> None:
    """Shortens the distance `cf:rogue-scoundrel-f1s2` asks a move to
    cover. That row is declared, so the name is not the hold -- the 3 is
    a literal inside its printed text and that feature is itself
    unwritten, so there is neither a number to rewrite nor a check to
    move it on."""


@power("f2459", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTEND_SHIFT)
def f2459(c: Cast) -> None:
    """Every shift is a square longer, at the price of combat advantage.
    A shift is taken inside the granting row's body with its distance
    already decided; `c.forces` lengthens a push and there is no twin of
    it for a shift. `ranger_b.f2361` and f2362 above want the same
    verb."""


@power("f2468", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.advantage_on_roll()",))
def f2468(c: Cast) -> None:
    """Roll two Stealth checks and keep the better after using `p1217`.
    The trigger is a ref and `skills.check` rolls one die with no way to
    ask for two -- `c.reroll_check` answers a check already made, which
    is a different and worse bargain."""


@power("f2890", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.feint()",))
def f2890(c: Cast) -> None:
    """Feinting with Bluff, and a bigger payout against whoever fell for
    it. Both printed clauses hang on the feint and there is none in the
    action menu -- neither a check to put the +2 on nor a success to
    trigger the rest. The payout half alone would be writable now:
    `c.bonus("cf:rogue-scoundrel-f4 damage", 0, dice="1d6")` is the
    extra die, since `extra_damage` reads that key beside its own."""
