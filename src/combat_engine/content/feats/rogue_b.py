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

* the **latch**, which is no longer shut and was the premise of the two
  bullets this list used to open with. It was a dict inside
  `extra_damage` keyed on the turn; it is `Powers.latched` on the
  creature now, `c.latched`/`c.latch`/`c.unlatch` reach it, and
  `strikers.pay_extra` is the shared payout that asks it before paying.
  #569.

  So "this use does not count" is a `c.unlatch` and a widening of the
  condition is a second `Hit` watcher paying through `pay_extra` --
  whichever watcher reaches a hit first pays and the other declines, in
  either order, which is why no second counter is needed. f2076 is
  written off exactly that. What is still here is the workaround built
  on the dead premise: `_window`, `_round_of`, `_watch_payout`, `_pay`
  and `_spare_use` below hand out a spare payout for later because "the
  latch itself cannot be reset", and f818 and f2426 still read them.
  They play correctly and can be replaced by the verbs.
* the **dice**, which are rolled inside `c.damage` and gone *by the time
  `DamageRolled` carries them*. `c.bonus` reaches the total --
  `c.bonus("cf:rogue-scoundrel-f4 damage", n)` is what `extra_damage`
  adds on top, and `dice=` puts a whole die there -- and rerolling a low
  one is no longer missing: `c.reroll_ones` is a floor read *before* the
  roll, inside `Cast._roll_damage`, narrowed by the ref of the row doing
  the rolling. f1661 is written against that. What is still shut is
  taking a die back **out**, which f952 wants: a `DamageRolled` listener
  has one summed number and no die to decline.

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

from combat_engine.content.features.strikers import pay_extra
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    REF,
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
    Moved,
    PowerResolved,
    SkillCheck,
)
from combat_engine.engine.query import allies, has_combat_advantage

from .styles import (
    among,
    hit_with_one_of,
    longer_shift_on_a_martial_hit,
    used_one_of,
)

#: **Retired.** It named "*when* the extra damage applies is a callable
#: closed over inside `strikers.extra_damage`, and a feat that widens it
#: has nothing to widen". The latch that made a second watcher unsafe is
#: `Powers.latched` on the creature now and `strikers.pay_extra` is the
#: shared payout that asks it, so a widening is a second `Hit` watcher
#: paying through the same door -- `f2076` is written off that. #569.
#: One weapon group standing in for another, for named rows only.
#: Nothing adds to the distance somebody else's shift covers.
#: **Retired: the two rows that shared it want different things.**
#: `c.extend_every` landed the class form -- lengthen every move of a
#: kind, not one named row -- and `f1393`, `f2263`, `f2360`, `f2361` and
#: `f2469` are written off it. What is left on the two rows here is not
#: the extension at all, and it is not the *same* leftover on both, so
#: one symbol cannot go red or green correctly for either. A marker names
#: one gap. See `f2362` and `f2459` below.

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


def _shot_range(c: Cast, *groups: str) -> int:
    """How far the thing in hand actually shoots, in squares. 0 if nothing.

    The **normal** range and not the long one: a long shot is legal and
    takes the -2 `resolve._long_range` charges, and that penalty is read
    off the row's own printed range line -- which a melee row stretched
    by a `"reach"` modifier has not got. So the conservative half of the
    two is the only one that can be charged correctly.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return 0
    for w in gear.held:
        if w.group in groups and w.ranged is not None:
            return w.ranged[0]
    return 0


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
       reach=PERSONAL, target=SELF, dropped=("c.extend_move(mid_move=)",),
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
       reach=PERSONAL, target=SELF)
def f2362(c: Cast) -> None:
    """Both printed benefits, as two watches armed when the feat arms.

    **`Power.second_trigger` was not the gap, and a second trigger would
    not have closed it.** The old note was right that this row's declared
    `on=` made its body run only when `p4488` resolved, and right that the
    other clause answers a hit with any martial encounter or daily power.
    It was wrong about the remedy twice over:

    * a header may **already** declare several triggers -- `on=` takes a
      sequence, `Power.triggers` is the one accessor every reader goes
      through, and **195 rows in the tree do it**. So the named symbol
      described something that exists;
    * and it still would not have helped, because
      `styles.longer_shift_on_a_martial_hit` *arms a watch*
      (`c.watch(Hit, …, until=When.ENCOUNTER)`). It needs the body to run
      **once at the start of the fight**, and a row with any declared
      trigger never does -- `turns.arm_traits` skips those deliberately,
      since arming a triggered row would fire it out of nowhere.

    So this is the `f1395` shape that `content/CLAUDE.md` already names for
    "a standing clause and a triggered one on the same card", and it is
    what `ranger_b.f2361` and `fighter_c.f2360` -- the same card printed
    once per class -- have been doing all along. This row was the odd one
    out.

    **"After the attack" is still `PowerResolved` and not `PowerUsed`**:
    the two are the same row's bookends and picking the wrong one puts the
    shift on the far side of the swing from where the card prints it. Only
    the *route* to that event changed, from a declared trigger to a watch.

    **`c.may` is new and is not decoration.** The card says "you **can**
    use a free action to shift", and under a declared trigger the choice
    was the dispatcher's -- it offers the row and the player declines. A
    watch has nobody to decline to, so the ask has to be explicit or the
    shift becomes compulsory.
    """
    def after(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        if getattr(ev, "power", "") != "p4488" or not _holding(c, "light blade"):
            return
        if c.may("shift 2 squares and try to go unseen"):
            _slip_away(c, 2)

    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=c.me, label=c.ref)
    longer_shift_on_a_martial_hit(c, lambda: _holding(c, "light blade"))


@power("f2338", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignore_requirement(ref)",),
       trigger="you attack with a bow or a crossbow")
def f2338(c: Cast) -> None:
    """No reprisal from the creature you are shooting at, and the named
    melee rows carry to the bow's range.

    A trait with a watcher in it rather than a declared trigger, which is
    the shape `ranger_b.f2337` already has and which the second benefit
    forces. A melee row's reach is read where the *area* is worked out --
    `dsl.area_of` asks `_stretched` before anybody has chosen a target --
    so a modifier laid from an `AttackDeclared` body arrives after the one
    question it answers, and the row could never be aimed past a square.
    Armed at the start of the fight, it stands while the area is offered.

    The watch is `Window.BEFORE` for the reason `f2337`'s is: the
    provocation happens as the shot is taken, and an `AFTER` window hands
    over the exemption once the reprisal has been made. `from_=` names
    the one creature the card exempts, which is not the same as not
    provoking at all.

    `c.as_ranged` *is* the second benefit -- a `"reach"` bonus -- and the
    one thing it cannot do is narrow to a list of rows. `_stretched` is
    handed a context carrying `power`, so `styles.among` is that filter,
    and the holding question is asked in the same gate rather than at
    arming, for the reason `ranger_b._wields` exists: a rogue who sheathes
    the bow stops having the benefit.

    No melee gate, unlike `c.as_ranged`'s own: `_stretched` reads
    `"reach"` **only** when the range kind is melee -- a ranged line reads
    `"range"` and a spread reads `"blast_size"` -- so the kind test there
    can never be false and is not copied here.

    Dropped: shooting a crossbow at a row whose Requirement prints a
    light blade. `Power.requires` is asked by `dsl.usable` and nothing
    standing on the creature relaxes it.
    """
    me = c.me
    far = _shot_range(c, "bow", "crossbow")
    if far:
        c.bonus(
            "reach", far - 1, on=me, until=When.ENCOUNTER, stacks=False,
            when=lambda ctx: (
                among("p4488", "p1387")(ctx)
                and _holding(c, "bow", "crossbow")
            ),
        )

    def exempt(ev: Any) -> None:
        if ev.attacker != me or not _holding(c, "bow", "crossbow"):
            return
        c.no_provoke(from_=ev.target, on=me, until=When.EOT)

    c.watch(
        AttackDeclared, exempt, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE,
    )


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
       reach=PERSONAL, target=SELF,
       implemented_in=("cf:rogue-scoundrel-f4",))
def f952(c: Cast) -> None:
    """Forgoes one die of the extra damage to lay an attack penalty. The
    payout is announced -- `DamageRolled` carries the label and the
    amount, and a `BEFORE` listener may change it -- but the dice are
    already summed into that number, so there is no die to decline.
    Subtracting a fresh roll instead would be a different distribution
    dressed up as the printed one."""


@power("f1661", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, used_one_of("p8278"), "you use p8278"))
def f1661(c: Cast) -> None:
    """Re-read: the old note was looking at the wrong event.

    `DamageRolled` does carry one total with the faces gone -- but
    `c.reroll_ones` is not read there. It records a floor that
    `Cast._roll_damage` consults *before* rolling, where the dice are in
    hand, and `_reroll_floor` narrows by `@<ref>` against the ref of the
    row doing the rolling. `strikers.extra_damage` rolls through the
    feature's own `Cast`, so that ref is `_SNEAK` and the floor lands on
    the extra dice alone. `below=3` is the card's "a 1 or a 2", and
    `_rolled_above` loops per die, which is its "reroll until a given die
    has a result greater than 2".

    `p8278` carries the necrotic keyword itself, so the printed damage
    type needs no second gate. The hold is opened above the body and
    shut on `PowerResolved` rather than left to the end of the turn:
    the rogue may pay its extra damage again on somebody else's turn,
    and only this power's swing is meant to reroll."""
    me = c.me
    held = c.reroll_ones(below=3, ref=_SNEAK, on=me, until=When.EOT)
    if held is None:
        return

    def shut(ev: PowerResolved) -> None:
        if ev.actor == me and ev.power == "p8278":
            c.end_effect(held)

    c.watch(PowerResolved, shut, until=When.EOT, on=me, label=c.ref)


@power("f2076", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2076(c: Cast) -> None:
    """Pays the extra damage without combat advantage when you are the only
    creature beside the target.

    **The objection in the old note is spent, because the latch moved.** It
    read "widening it from out here means a second watcher with a latch of
    its own -- which pays twice in any turn that has one hit of each kind
    in it". `strikers.pay_extra` is the shared payout and opens by asking
    `c.latched`, so whichever of the two watchers reaches a hit first pays
    and the other declines -- in either order, which is `f1722`'s own
    reasoning for the ranger. The latch is `Powers.latched` on the
    creature rather than a dict inside `extra_damage`'s closure. #569.

    So this is a strictly disjoint widening of the feature's `applies=`:
    that gate is combat advantage and nothing else, and one hit satisfying
    both conditions still pays exactly once.

    `side="other"` and not `"any"`: the circle is centred on the target and
    `"any"` would count the target itself, so the comparison would never
    be true. `"other"` is the pool with the centre left out, which makes
    `== [me]` the printed "you are the only creature adjacent to it".

    The rapier is asked by ref rather than as the light-blade group, for
    the module docstring's reason -- the dagger every rogue starts with is
    a light blade and is not a rapier.
    """
    me = c.me

    def also(ev: Hit) -> None:
        if ev.attacker != me or not _holding_ref(c, *_RAPIER):
            return
        if c.within(1, of=ev.target, side="other") != [me]:
            return
        pay_extra(c, _SNEAK, c.sneak_damage(), on=ev.target, per_turn=True)

    c.watch(Hit, also, until=When.ENCOUNTER, on=me, label=c.ref)


# -- one weapon group standing in for another -------------------------------


def _counts_as(
    ref: str,
    what: str,
    *,
    waives: tuple[tuple[str, str], ...] = (),
    wants: tuple[str, ...] = (),
) -> None:
    """A feat whose whole benefit is one weapon standing in for another.

    `waives` is `(holding, satisfies)` pairs, matched the way a printed
    Requirement is -- by group, category, property or printed slug -- so a
    card naming a group waives it for every weapon in that group and a card
    naming one weapon waives it for that one.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants or ())
    def feat(c: Cast) -> None:
        for holding, satisfies in waives:
            c.counts_as(satisfies, holding=holding)

    feat.__name__ = ref
    feat.__doc__ = what


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
       reach=PERSONAL, target=SELF)
def f821(c: Cast) -> None:
    """A mace where the rows ask for a light blade, at the cost of a die of
    the extra damage.

    The price is written. The swap is the dropped clause: `c.as_implement`
    rewrites a weapon's group outright, and the general form -- count as a
    light blade *for these rows only* -- has no verb. `rogue.py`'s f799 named
    it first.

    Both halves are written now. The swap is keyed on the **group**, which
    is `mace` for a mace and for a club both, and the price is a die off the
    class's extra damage while one is in hand."""
    c.counts_as("light blade", holding="mace")
    _price(c, ("mace",))


@power("f825", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f825(c: Cast) -> None:
    """An axe, a hammer or a pick where the rows ask for a light blade, at the
    cost of a die of the extra damage.

    `f821` with three groups instead of one, and both halves written. "With
    one hand" is on the card and is not expressed: the waiver is matched by
    one word, so a two-handed axe is let through as well."""
    for group in ("axe", "hammer", "pick"):
        c.counts_as("light blade", holding=group)
    _price(c, ("axe", "hammer", "pick"))


_counts_as(
    "f2078",
    """A one-handed heavy blade where the rows ask for a light blade, the
    extra damage included. The proficiency half is a column and not a body.

    Keyed on the **group**, so every heavy blade answers. "One-handed" and
    "military" narrow it on the card and are not expressed: the waiver is
    matched by one word, so a two-handed heavy blade is let through too.
    Named rather than left silent.
    """,
    waives=(("heavy blade", "light blade"),),
)
_counts_as(
    "f2437",
    """A hammer where the rows ask for a light blade.

    Keyed on the group rather than on the two printed weapons, which is
    both shorter and more correct here: the card names a warhammer and a
    throwing hammer, and **the throwing hammer has no row in the weapon
    table at all** -- the group covers it anyway.
    """,
    waives=(("hammer", "light blade"),),
)
_counts_as(
    "f2471",
    """A bow where the rows ask for a crossbow. The extra damage already
    takes a bow -- `strikers._SNEAK_GROUPS` has it -- so what this adds is
    the rogue powers.""",
    waives=(("bow", "crossbow"),),
)
_counts_as(
    "f2895",
    """A shortbow where the rows ask for a crossbow. The proficiency half
    is a column.

    By slug, not by group: `f2471` is the card that waives every bow, and
    this one names the short one only.
    """,
    waives=(("shortbow", "crossbow"),),
)


# -- the rest of the gaps, each named exactly -------------------------------


@power("f826", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Gear.off(ranged=)", "c.reload()"))
def f826(c: Cast) -> None:
    """A hand crossbow held in the off hand and reloaded one-handed.

    **Re-pointed, not closed.** `Weapon.off_hand_anyway` was the wrong
    symbol and is retired everywhere else: no two-weapon reader consults a
    property at all -- `Gear.off` is `melee[1]`, `Gear.two_weapon` counts
    melee weapons -- so writing the word onto this card's weapon would buy
    nothing. What the card needs is for the slot itself to hold a shooter.
    This weapon is ranged, `Gear.melee` excludes it, and so it can never be
    `Gear.off` however its properties read. That is a `Gear` change, and
    `Gear.off(ranged=)` names it.

    Loading is the second gap and is untouched, so the free shot on a
    critical has two unaskable halves: which weapon is in the off hand, and
    whether it is loaded."""


@power("f2073", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2073(c: Cast) -> None:
    """A light shield's bonus to defences rises to +2, which is +1 more.

    Both halves are answerable now: `Gear.shield` says *which* shield and
    `c.shield_bonus()` what it is worth. Gated on the light one, because a
    heavy shield already grants 2 and the card raises only the light.

    `kind="shield"` so it reads as the same bonus getting larger rather
    than a second one stacking on top.
    """
    if c.shield_bonus() != 1:
        return
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="shield")
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, kind="shield")


@power("f2074", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_power_bonus()",))
def f2074(c: Cast) -> None:
    """Adds one to a power bonus to defences while a light shield is
    carried.

    **Down to one gap.** Which shield it is can be asked now --
    `c.shield_bonus() == 1` is the light one. What is still missing is the
    other half: a bonus being laid announces nothing a row can answer.
    `Mods` records the number and its kind, not the act of granting it, so
    there is no moment at which to add the +1."""


@power("f2405", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2405(c: Cast) -> None:
    """Slings gain the high crit property, and print a better proficiency
    bonus. Both halves are written.

    **"Any way to rewrite the weapon a character is holding" exists**, and
    the premise under that note -- `Weapon` being "read off the item rather
    than off the wielder" -- stopped holding when `Gear.weapons` started
    carrying `replace(w)` copies. `c.gains_property` is the writer and
    `_high_crit` is the reader. #676.

    **The proficiency half is a set and not a bonus**, which is the whole
    reason it waited for a writer rather than being spelled with
    `c.bonus`. The card says "treat slings as having a +3 proficiency
    bonus"; `w3628` prints **2**, and the held weapon's printed figure is
    already added to every swing. Measured again on `w3612`, forcing a
    natural 10: proficiency 0/2/3/5 gives totals 17/19/20/22, one point of
    attack per point. So `c.bonus("attack", 3, kind="proficiency")` would
    pay 3 on top of the 2 already there -- too generous rather than inert,
    which is the kind nothing notices. `c.weapon_proficiency` sets it.

    The old note here pointed at `cast.py:1748` for the reader. That line
    is in the middle of an unrelated docstring now; the measurement above
    is what establishes the reader, and it is the honest form of the
    claim.

    `f3784` lays a flat +2 for unarmed and is right, because unarmed prints
    0: there the delta and the printed figure coincide, which is why it
    does not settle this case."""
    c.gains_property("high crit", group="sling", on=c.me)
    c.weapon_proficiency(3, group="sling", on=c.me)


@power("f2429", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:rogue-scoundrel-f1s2",))
def f2429(c: Cast) -> None:
    """Shortens the distance `cf:rogue-scoundrel-f1s2` asks a move to
    cover. That row is declared, so the name is not the hold -- the 3 is
    a literal inside its printed text and that feature is itself
    unwritten, so there is neither a number to rewrite nor a check to
    move it on.

    **Re-aimed off `c.change_distance(ref, n)`, which has existed all
    along under another name.** `c.extend_move(ref, squares)` is "make a
    named row move you further", keyed by ref, and `c.squares_for` is its
    read half -- the entries add, so a *negative* entry shortens, which is
    this card exactly. Its own docstring names what is actually missing:
    "a row must read it to be changed, with `squares_for`. An
    `extend_move` on a row whose body still hard-codes its distance is a
    modifier nothing consults."

    So the hold is the sibling row, not a verb, and the marker names the
    sibling. `cf:rogue-scoundrel-f1s2` has an empty body and waits on
    `c.stealth_speed()` and `c.hide(cover=)`; marking either of those here
    would report this feat ready the day a symbol lands, which is one step
    early -- the feature has to be *written* before there is a 3 to take a
    square off."""


@power("f2459", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2459(c: Cast) -> None:
    """Every shift is a square longer, at the price of combat advantage.

    **The word that was missing was "if".** The card reads "you *can* shift
    1 additional square. **If you do so**, you grant combat advantage until
    the start of your next turn." `c.extend_every` adds to the shift's
    *budget* and `World.decide` need not spend it, so whether the clause was
    taken was not observable -- and laying the +1 alone would have made this
    feat strictly better than the one on the page. That is why it kept
    `todo=` rather than taking `dropped=`: the missing clause was a **cost**,
    and a row that plays with its cost missing is not incomplete, it is
    wrong.

    `Moved.stretched_` is that observation -- how many squares beyond the
    printed distance were actually **spent**, as a plain attribute the way
    `kind_` rides, for the reason `kind_` is one: a field would reach the
    wire and every replay fixture, and this is not a change in how a fight
    resolves. #572.

    So the cost is charged on the move and not on the grant, which is what
    the card says: shift your printed distance and nothing happens; take the
    extra square and the advantage falls due. `kind_` is checked as well as
    `stretched_`, because a *walk* lengthened by something else is not this
    clause -- the card says "whenever you shift".

    `When.SONT` is "until the start of your next turn", printed.

    `AT_WILL`: the card prints no limit, and an `ENCOUNTER` triggered trait
    is spent by its first firing -- the correction `lint.py` made to `f807`
    and to `f2257`.
    """
    c.extend_every("shift", 1, until=When.ENCOUNTER)

    def paid(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        if getattr(ev, "kind_", "") != "shift":
            return
        if getattr(ev, "stretched_", 0) <= 0:
            return
        # **`to="enemies"`, and the default would have been wrong.**
        # `grants_advantage(on=X)` means *X grants it*, and `to=` names who
        # gains -- defaulting to `"me"`, the caster. On a row the caster
        # casts on itself that reads as "I grant combat advantage to
        # myself", which is nothing. The card says the square is paid for
        # with advantage to everyone swinging at me.
        c.grants_advantage(on=c.me, to="enemies", until=When.SONT)

    c.watch(Moved, paid, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("f2468", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1217 during your turn",
       on=Trigger(PowerUsed, used_one_of("p1217"), "you use p1217"))
def f2468(c: Cast) -> None:
    """Two rolls and the higher on every Stealth check for the rest of the
    turn, bought by using `p1217`.

    **"A different and worse bargain" was an argument and not a
    measurement, and it was wrong.** `c.reroll_check(keep="best")` rolls a
    second d20 and keeps `max(old, fresh)`, which is the same distribution
    as throwing two at once; `general_i.f1376b` settles the family in
    those words for the identical printed sentence.

    **A watch, not a modifier**, because the clause is about *how* a later
    roll is made rather than what it adds, and those rolls have not
    happened yet. `ev=` is required and is the whole reason the verb takes
    it: a handler closes over this row's `Cast`, whose `trigger` is the
    `PowerUsed` that armed the watch and not the check being watched.

    The default `Window.AFTER` is right -- `skills.check` totals inside its
    resolve callback, so a row answering afterwards still decides what the
    check came to.

    `When.EOT` is the printed "before the end of your turn" and every check
    inside it, so no `once=`.

    `AT_WILL`: the card prints no limit, and a triggered `action=NONE` row
    declared `ENCOUNTER` is spent on its first firing -- the correction
    `lint.py` made to `f1661` in this file.
    """
    def twice(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        if getattr(ev, "skill", "") != "stealth":
            return
        if c.may("roll twice and use the higher result"):
            c.reroll_check(keep="best", ev=ev)

    c.watch(SkillCheck, twice, on=c.me, until=When.EOT, label=c.ref)


@power("f2890", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.feint()",))
def f2890(c: Cast) -> None:
    """Feinting with Bluff, and a bigger payout against whoever fell for
    it. Both printed clauses hang on the feint and there is none in the
    action menu -- neither a check to put the +2 on nor a success to
    trigger the rest. The payout half alone would be writable now:
    `c.bonus("cf:rogue-scoundrel-f4 damage", 0, dice="1d6")` is the
    extra die, since `extra_damage` reads that key beside its own."""
