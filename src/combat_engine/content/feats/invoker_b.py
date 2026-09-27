"""Invoker feats, the second batch.

`invoker.py` holds the first. Almost every row here hangs off the class's
one big fork -- which covenant was taken -- and that fork is askable:
`chargen.BUILDS["invoker"]` carries `wrath`, `preservation` and
`malediction`, so `c.build(...)` answers and three rows branch on it.

Two shapes make up most of the list.

**"A divine encounter or daily attack power"** is writable and is the
spine of eight rows: `Keyword.DIVINE` plus `p.usage` plus `p.is_attack`,
read off the resolved row exactly the way `cf:invoker-f1` reads it.
`PowerResolved` rather than `PowerUsed`, for the same reason that feature
gives -- the printed line is about what the power did, and `PowerUsed`
fires before the body.

**A power the benefit names in prose** is the rest. The covenant's two
channelled invocations and the two covenant reactions all arrive as
names rather than as refs, so the rows riding on them carry
`c.class_feature()`. Four of those specs point at `m5994a3`: that is a
monster's stat block, which the importer's name index landed on when it
tried to resolve a class-feature name, so it is an unresolved name and not
a ref to read.

Where a ref *is* given -- `p5186` and `p7150` in a prerequisite, `p7151`,
`p8278`, `f2023b`, and the four racial powers -- the row is written
against it, the same rule `avenger_b.py` follows for `p5331`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    Size,
    Summoned,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    about_me,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import ForcedMove, PowerResolved
from combat_engine.engine.query import alive

#: A class feature the benefit names in prose with no ref -- the covenant's
#: channelled invocations and its two reactions.
FEATURE = ("c.class_feature()",)
#: A racial power the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)
#: Nothing adds a keyword to a row, or makes one count as another sort.
COUNTS_AS = "c.counts_as(keyword=)"
#: "Instead of your covenant manifestation": nothing declines a class
#: feature's payout for one use of one power.
SUPPRESS = ("c.suppress_feature()",)
#: `c.grants_advantage` takes no `when=`, so combat advantage cannot be
#: narrowed to one shape of power.
NARROW_CA = ("c.grants_advantage(when=)",)

#: What the covenant's own feature calls a power big enough to manifest.
_BIG = (Usage.ENCOUNTER, Usage.DAILY)


def _divine(ref: str) -> bool:
    """"An invoker power" is read as a divine one, as `f483` already does:
    the engine has no per-class keyword."""
    p = get(ref)
    return p is not None and Keyword.DIVINE in p.keywords


def _big_attack(ref: str, usages: tuple[Usage, ...] = _BIG) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.DIVINE in p.keywords
        and p.usage in usages
        and p.is_attack
    )


def _mine_on_my_turn(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and world.turn == me and _big_attack(ev.power)


def _mine_daily(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.actor == me
        and world.turn == me
        and _big_attack(ev.power, (Usage.DAILY,))
    )


def _mine_at_range(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and _big_attack(ev.power)
        and p is not None
        and p.reach.kind == "ranged"
    )


def _missed_everyone(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.actor == me
        and _big_attack(ev.power, (Usage.DAILY,))
        and not any(getattr(r, "hit", False) for r in ev.rolls)
    )


def _struck(world, ev: Any) -> list[int]:  # noqa: ANN001
    """Who this use actually hit. `PowerResolved.rolls` is the only place
    that says so for a whole use at once."""
    hurt = [r.target for r in ev.rolls if getattr(r, "hit", False)]
    return [t for t in dict.fromkeys(hurt) if alive(world, t)]


_CARD_A = "cf:invoker-f1c0"
_CARD_B = "cf:invoker-f1c1"


def _card_ally(ev: Any) -> int | None:
    """The ally `cf:invoker-f1c0` was played for.

    That card is `NO_TARGET` and reads its pair off its own trigger, so
    `PowerUsed.targets` is empty; the ally is one event down, on the
    `Hit` the card answered.
    """
    return getattr(getattr(ev, "trigger", None), "target", None)


def _card_foe(ev: Any) -> int | None:
    """The enemy off a covenant card's trigger.

    Not `ev.targets`: `cf:invoker-f1c1` declares `target=ONE_CREATURE`
    and then aims at this creature with `on=`, so the list names whoever
    the burst happened to pick and never the one the card burned.
    """
    return getattr(getattr(ev, "trigger", None), "attacker", None)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _in_my_zone(c: Cast, ref: str) -> bool:
    """Is the caster standing in a zone its own named row laid?

    Nothing asks membership of a zone by ref -- `c.my_zones` gives ids and
    `c.in_my_aura` only answers for auras -- so the squares are read off
    the zone. `Cast.zone` labels one with the ref that laid it when the
    row passes no `label=`, which is how `p2473` is found.
    """
    return any(
        zone.owner == c.me and zone.label == ref and c.here in zone.squares
        for _zid, zone in c.world.zones.all()
    )


def _hit_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _ranged_divine_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.DIVINE in p.keywords
        and p.reach.kind == "ranged"
    )


# -- riders on "a divine encounter or daily attack power" -------------------


@power("f1494", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f1494(c: Cast) -> None:
    """The penalty is only against *you*, which is a gate on the attack
    context rather than a flat -2: `ctx["target"]` is the creature being
    swung at, so the same enemy hits everybody else unhindered."""
    me = c.me
    for foe in _struck(c.world, c.trigger):
        c.penalty(
            "attack", 2, on=foe, until=When.SONT,
            when=lambda ctx: ctx.get("target") == me,
        )


@power("f1539", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f1539(c: Cast) -> None:
    """"His or her next saving throw" is `once=True` on a save modifier:
    the hold expires with the turn either way, and the bonus is spent by
    the first throw rolled under it."""
    friends = [a for a in c.within(10, side="ally") if a != c.me]
    who = c.choose(friends, f"{c.ref}: which ally is steadied")
    if who is not None:
        c.bonus("save", 1, on=who, until=When.EONT, kind="power", once=True)


@power("f1540", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f1540(c: Cast) -> None:
    """"All defenses" is four modifiers; there is no single key for them."""
    friends = [a for a in c.within(10, side="ally") if a != c.me]
    who = c.choose(friends, f"{c.ref}: which ally is shielded")
    if who is None:
        return
    for guarded in (AC, FORT, REF, WILL):
        c.bonus(guarded, 1, on=who, until=When.EONT, kind="power")


@power("f1548", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=SUPPRESS,
       trigger="you use a divine daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_daily, "your daily invocation resolves"))
def f1548(c: Cast) -> None:
    """The pull is written and "instead of the normal benefit of your
    covenant manifestation" is dropped: `cf:invoker-f1` arms its own
    watch for the encounter and nothing declines one payout of it."""
    for friend in c.within(5, side="ally"):
        if friend != c.me:
            c.pull(1, on=friend)


@power("f2285", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=SUPPRESS,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f2285(c: Cast) -> None:
    """The goaded enemy needs somebody to swing at, and the printed line
    does not name one -- so the victim is whoever of mine is standing
    beside it. With nobody in reach there is no attack and therefore no
    backlash, which is the printed conditional rather than a shortcut.

    The paragon and epic steps of the burn are out of scope.
    """
    struck = _struck(c.world, c.trigger)
    foe = c.choose(struck, f"{c.ref}: which target is goaded", optional=True)
    if foe is None:
        return
    reachable = [a for a in c.within(1, side="ally") if c.adjacent_to(foe, a)]
    if not reachable:
        return
    if c.grant_attack(foe, on=reachable[0]):
        c.flat(5 + c.int_mod, dtype=DamageType.FIRE, on=foe)


@power("f2751", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=SUPPRESS,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f2751(c: Cast) -> None:
    """Same drop as f1548. `c.save` follows the target, so the ally is
    named."""
    friends = [a for a in c.within(10, side="ally") if a != c.me]
    who = c.choose(friends, f"{c.ref}: which ally throws off an effect")
    if who is not None:
        c.save(on=who)


@power("f2981", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit only one target with a ranged invoker encounter or daily attack",
       on=Trigger(PowerResolved, _mine_at_range, "your ranged invocation resolves"))
def f2981(c: Cast) -> None:
    """"Only one target" is counted off what was *hit*, not off what was
    aimed at -- a burst that catches three and hits one is the case the
    clause is for. "After the power's effect is resolved" is why this is
    `PowerResolved` and not `Hit`."""
    struck = _struck(c.world, c.trigger)
    if len(struck) == 1:
        c.slide(1, on=struck[0])


@power("f2990", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss every target with a daily invoker attack power",
       on=Trigger(PowerResolved, _missed_everyone, "your daily missed"))
def f2990(c: Cast) -> None:
    """`p7151` is named by the prerequisite. `c.recast` is the whole
    printed benefit -- a second, cheaper entry in the menu for a row the
    invoker already knows -- and `When.EOT` is "before the end of your
    turn"."""
    c.recast("p7151", action=ActionType.MINOR, per_turn=1, until=When.EOT)


# -- the covenant itself ----------------------------------------------------


@power("f2982", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2982(c: Cast) -> None:
    """Three riders on `p5186`, one per covenant, and the prerequisite
    names the row so all three are writable.

    Written as a trait with a watch rather than with a declared trigger,
    because the wrath leg is a standing modifier and the other two are
    triggered: a row cannot hold both. The wrath leg is `c.forces` gated
    on the power, which is exactly "2 + Constitution instead of 2".
    """
    me = c.me
    if c.build("wrath"):
        c.forces(
            max(0, c.con_mod), on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p5186",
        )
        return
    cursing = c.build("malediction")

    def after(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "p5186":
            return
        if cursing:
            c.penalty("attack", 2, on=ev.target, until=When.EONT)
        else:
            c.slowed(on=ev.target, until=When.EONT)

    c.watch(Hit, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} rebuke")


@power("f2985", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7150",
       on=Trigger(PowerUsed, _used("p7150"), "you use that invocation"))
def f2985(c: Cast) -> None:
    """The prerequisite names the channelled row, so this is one of the
    three in the batch that does not carry `c.class_feature()`. "Target",
    not "hit", so `PowerUsed.targets` is the right set and firing before
    the body does no harm -- targets are chosen first."""
    for foe in c.trigger.targets:
        c.penalty("damage", c.wis_mod, on=foe, until=When.EONT)


@power("f2998", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2998(c: Cast) -> None:
    """A covenant rider on everything this invoker summons.

    `x6_679` in the spec is an unresolved word rather than a ref, and the
    sentence reads the same without it. Nothing relates a summon to its
    summoner -- `c.summon` does not bind -- but `Summoned` carries both
    ends, and every path that puts a creature on the board emits it, so
    the arrival is where each leg is laid.
    """
    me = c.me

    def arrived(ev: Summoned) -> None:
        if ev.actor != me:
            return
        thing = ev.summon
        if c.build("wrath"):
            c.bonus(
                "damage", c.con_mod, on=thing, until=When.ENCOUNTER, kind="feat"
            )
        elif c.build("malediction"):
            ring = c.aura(1, on=thing, until=When.ENCOUNTER, label=f"{c.ref} dread")
            c.grants_in(ring, "attack", -1, side="enemy", kind="untyped")
        else:

            def begun(turn: TurnStart) -> None:
                if turn.actor in c.allies() and c.adjacent_to(thing, turn.actor):
                    c.shift_as(
                        ActionType.MINOR, 1, on=turn.actor, until=When.EOT
                    )

            c.watch(
                TurnStart, begun, until=When.ENCOUNTER, on=me,
                label=f"{c.ref} succour",
            )

    c.watch(Summoned, arrived, until=When.ENCOUNTER, on=me, label=f"{c.ref} host")


@power("f2984", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2984(c: Cast) -> None:
    """Adjacency is asked at the end of the enemy's turn, which is what the
    sentence says and also the only moment it is true of a creature that
    walked past. The summons are collected off `Summoned` for the same
    reason f2998 does it."""
    me = c.me
    mine: list[int] = []

    def arrived(ev: Summoned) -> None:
        if ev.actor == me:
            mine.append(ev.summon)

    def ended(ev: TurnEnd) -> None:
        who = ev.actor
        if who not in c.enemies():
            return
        if any(alive(c.world, s) and c.adjacent_to(s, who) for s in mine):
            c.slowed(on=who, until=When.EOTNT)

    c.watch(Summoned, arrived, until=When.ENCOUNTER, on=me, label=f"{c.ref} host")
    c.watch(TurnEnd, ended, until=When.ENCOUNTER, on=me, label=f"{c.ref} mire")


@power("f2989", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f2989(c: Cast) -> None:
    """Swaps the covenant manifestation for another covenant's between
    fights. `c.build` reads the leg and nothing writes one, so the whole
    benefit is the gap -- the same symbol the multiclass feats name."""


# -- riders on powers the spec names in prose -------------------------------


@power("f1506", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f1506(c: Cast) -> None:
    """Intelligence on the damage of the attack that card's bonus helps.

    Written as the damage-side twin of the card's own attack bonus: same
    enemy, same window, same `once=True`, so the two are spent on the
    same swing. The damage context carries `target`, which is the whole
    of the gate this needs."""
    foe = _card_foe(c.trigger)
    if foe is None or c.int_mod <= 0:
        return
    c.bonus(
        "damage", c.int_mod, until=When.EONT, on=c.me, once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f1521", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.race_option()",))
def f1521(c: Cast) -> None:
    """Five elemental variants of a bonus to the ally `cf:invoker-f1c0`
    protected. Re-aimed: the ally is on the card's trigger and that is
    carried now. Which of the five legs is current is not -- two of them
    are not damage types at all, so `c.element` cannot stand in, and
    `rt:r33-manifestation` carries the same marker."""


@power("f1525", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f1525(c: Cast) -> None:
    """A teleport for the ally `cf:invoker-f1c0` protected."""
    ally = _card_ally(c.trigger)
    if ally is not None:
        c.teleport(2, who=ally)


@power("f1549", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f1549(c: Cast) -> None:
    """Concealment for the ally that card was played for."""
    ally = _card_ally(c.trigger)
    if ally is not None:
        c.conceal(on=ally, until=When.EONT)


@power("f1748", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f1748(c: Cast) -> None:
    """Combat advantage when an attack roll `cf:invoker-f1c0` boosted
    lands.

    The card's bonus is spent inside its own closure, so the first hit on
    that enemy inside the card's window is what stands in for "the attack
    that gained the bonus" -- the two can only differ if the bonus was
    spent on a miss. Latched by hand rather than with `once=`, which is a
    bus-level once and would be spent by the first `Hit` of any kind.

    A bare "grants combat advantage" names no beneficiary, so it is the
    whole side.
    """
    foe = _card_foe(c.trigger)
    if foe is None:
        return
    spent = False

    def landed(ev: Hit, who: int = foe) -> None:
        nonlocal spent
        if spent or ev.attacker != c.me or ev.target != who:
            return
        spent = True
        c.grants_advantage(on=who, until=When.EONT, to="team")

    c.watch(Hit, landed, until=When.EONT)


@power("f2995", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f2995(c: Cast) -> None:
    """Insubstantial for the ally that covenant reaction answered for."""
    ally = _card_ally(c.trigger)
    if ally is not None:
        c.insubstantial(on=ally, until=When.SONT)


@power("f2996", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used(_CARD_A), "you use that covenant card"))
def f2996(c: Cast) -> None:
    """A slide and a mark cleared off the same ally."""
    ally = _card_ally(c.trigger)
    if ally is None:
        return
    c.slide(1, on=ally)
    c.cure(Condition.MARKED, on=ally)


@power("f1510", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=NARROW_CA,
       trigger="you use p7150",
       on=Trigger(PowerUsed, _used("p7150"), "you use that invocation"))
def f1510(c: Cast) -> None:
    """The invocation is `p7150` and the spec says so outright, so this is
    an ordinary rider now.

    `p7150` rolls no attack -- every enemy in the blast takes its effect --
    so "hit" is read as "targeted", and `PowerUsed.targets` is the set,
    chosen before the body and therefore trustworthy there. Same reading
    f2985 makes of the same row.

    "The next" is `once=True`, which ends the grant on the first attack
    roll against that creature. "Your allies but not you" is `to="ally"`,
    which reads as it does on `c.within`; it used to have no spelling and
    was being written as the caster's whole side.
    """
    for foe in c.trigger.targets:
        if c.is_kind("elemental", foe):
            c.grants_advantage(on=foe, to="ally", once=True, until=When.EONT)


#: "A fear, cold, or necrotic attack". The fear third is already
#: `p7150`'s own printed clause, so only the two new ones are laid here --
#: including fear would push twice for one blow.
_ALSO = (Keyword.COLD, Keyword.NECROTIC)


@power("f2006", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7150",
       on=Trigger(PowerUsed, _used("p7150"), "you use that invocation"))
def f2006(c: Cast) -> None:
    """Widens the push `p7150` already prints for fear attacks to cold and
    necrotic ones.

    "Under the effect of p7150" is its target list, which the row is handed
    before the body runs; the watch expires with the effect it tracks, at
    the end of the caster's next turn.

    Fear is deliberately left out of `_ALSO`: the invocation pushes for it
    itself, and listing it here would push twice.
    """
    me = c.me
    under = set(c.trigger.targets)

    def struck(ev: Hit) -> None:
        if ev.target not in under:
            return
        p = get(ev.power)
        if p is None or not any(k in p.keywords for k in _ALSO):
            return
        c.push(1, on=ev.target)

    c.watch(Hit, struck, until=When.EONT, on=me, label=c.ref)


#: Size has no ordering of its own -- the value is the word, and the
#: footprint is a property that collapses Tiny, Small and Medium together.
#: Declaration order is the ladder.
_SIZE_ORDER = {s: i for i, s in enumerate(Size)}


@power("f1562", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1562(c: Cast) -> None:
    """Wisdom on the damage `cf:invoker-f1c1` deals a larger enemy.

    The card burns its victim with `c.flat`, which goes through
    `deal_damage` and so through the damage modifiers -- and that context
    carries `power` and `target`, which is exactly the pair this needs. So
    the rider is one gated bonus on the caster rather than anything reached
    into the card, and it does not need the card's trigger.

    `Size` is a `StrEnum` with no ordering, so the ladder is its
    declaration order.
    """
    me = c.me
    mine = _SIZE_ORDER.get(c.size_of(me), 0)
    if c.wis_mod <= 0:
        return

    def bigger(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            ctx.get("power") == "cf:invoker-f1c1"
            and who is not None
            and _SIZE_ORDER.get(c.size_of(who), 0) > mine
        )

    c.bonus("damage", c.wis_mod, until=When.ENCOUNTER, on=me, when=bigger)


@power("f1563", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1563(c: Cast) -> None:
    """Prone after `cf:invoker-f1c1`'s push.

    The push is inside that card's body, but it is not private: `c.push`
    hands its own ref to `ForcedMove`, so the shove announces which row
    made it and the victim comes with it. No other event does -- `Moved`
    carries `kind_` and no power.

    Printed as a choice, so it is offered.
    """
    me = c.me

    def shoved(ev: ForcedMove) -> None:
        if ev.source != me or getattr(ev, "power", "") != "cf:invoker-f1c1":
            return
        if c.may("knock the pushed target prone", who=me):
            c.prone(on=ev.target)

    c.watch(ForcedMove, shoved, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2003", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c1",
       on=Trigger(PowerUsed, _used(_CARD_B), "you use that covenant card"))
def f2003(c: Cast) -> None:
    """Extra cold damage and an immobilise on the undead `cf:invoker-f1c1`
    burns.

    Declared on the use so the bloodied state can be read *before* the
    card lands, and paid out on the resolution so that the card's own
    radiant and this cold count as one attack for "if this attack
    bloodies" -- which is the difference between immobilising a creature
    this blow bloodied and immobilising one that was bloodied already.
    """
    foe = _card_foe(c.trigger)
    if foe is None or not c.is_kind("undead", on=foe):
        return
    was = c.bloodied(foe)

    def after(ev: PowerResolved, who: int = foe, before: bool = was) -> None:
        if ev.actor != c.me or ev.power != _CARD_B:
            return
        c.damage("1d6", dtype=DamageType.COLD, on=who)
        if c.bloodied(who) and not before:
            c.immobilized(on=who, until=When.EONT)

    c.watch(PowerResolved, after, until=When.EOT, once=True)


@power("f2874", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f2874(c: Cast) -> None:
    """Widens what sets that reaction off, from being hit yourself to an
    ally within 5 squares being hit.

    `cf:invoker-f1c1` is a declared row and its trigger is a declared
    `Trigger`, so the feature is no longer what this waits on. What is
    missing is a row reaching another row: nothing uses one, and nothing
    adds a second window to one that is already printed. The same
    absence f3041 names."""


@power("f2987", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="your covenant manifestation goes off inside your p2473",
       on=Trigger(PowerResolved, _mine_on_my_turn, "your invocation resolves"))
def f2987(c: Cast) -> None:
    """Concealment for an ally when the covenant manifestation goes off
    while you stand in your own racial zone.

    The manifestation has no event of its own: `cf:invoker-f1` hangs its
    payout on the same `PowerResolved` under the same gate, so "when you
    trigger it" is that gate repeated rather than anything read off the
    feature. The prerequisite is what guarantees the feature is there.

    `AT_WILL` because the card prints no limit, and a triggered
    `action=NONE` row spends a use every time it fires.
    """
    if not _in_my_zone(c, "p2473"):
        return
    friends = [a for a in c.within(10, side="ally") if a != c.me]
    who = c.choose(friends, f"{c.ref}: which ally is hidden", optional=True)
    if who is not None:
        c.conceal(on=who, until=When.EONT)


# -- racial riders ----------------------------------------------------------


@power("f1769", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1769(c: Cast) -> None:
    """`c.forces` is the one modifier that lengthens a shove from the
    shoving end, and its gate is handed the power -- so "with a divine
    power" is the gate rather than a flat extra square on everything."""
    c.forces(
        1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _divine(ctx.get("power", "")),
    )


@power("f2757", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=NARROW_CA,
       trigger="an enemy misses you with an attack",
       on=Trigger(Miss, targets_me, "an enemy misses you"))
def f2757(c: Cast) -> None:
    """The advantage is laid on the enemy that missed. Narrowing it to this
    character's own invocations is dropped: `c.grants_advantage` takes no
    `when=`, so the row also helps a plain weapon swing."""
    c.grants_advantage(on=c.trigger.attacker, until=When.EONT)


@power("f2988", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=NARROW_CA,
       trigger="you are bloodied for the first time this encounter",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f2988(c: Cast) -> None:
    """"The first time in an encounter" is what `usage=ENCOUNTER` already
    says: the row is spent by its first firing. The narrowing to close
    bursts and blasts is dropped, as in f2757."""
    for foe in c.enemies():
        c.grants_advantage(on=foe, until=When.EONT)


@power("f2992", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2483",
       on=Trigger(PowerUsed, _used("p2483"), "you use that racial power"))
def f2992(c: Cast) -> None:
    """Plain "+2 bonus" with no type word, so untyped. The damage context
    carries `power`, which is where the narrowing to divine rows lives."""
    c.bonus(
        "damage", 2, on=c.me, until=When.EONT,
        when=lambda ctx: _divine(ctx.get("power", "")),
    )


@power("f2993", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=SUPPRESS,
       trigger="you use p2484",
       on=Trigger(PowerUsed, _used("p2484"), "you use that racial power"))
def f2993(c: Cast) -> None:
    """A shift on every landed invocation for the rest of the fight. The
    "instead of your covenant manifestation" half is dropped, as in
    f1548."""
    me = c.me
    step = max(1, c.wis_mod)

    def after(ev: Hit) -> None:
        if ev.attacker == me and _big_attack(ev.power):
            c.shift(step)

    c.watch(Hit, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} stride")


@power("f2994", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.on_granted_basic()", COUNTS_AS),
       trigger="you use p7441",
       on=Trigger(PowerUsed, _used("p7441"), "you use that racial power"))
def f2994(c: Cast) -> None:
    """Three riders on three racial powers, all named by ref.

    `p7441`'s is written. `p7442`'s -- swapping a ranged basic in for the
    melee basic that power grants -- and `p7443`'s -- retyping that power's
    extra damage and adding a keyword to it -- are both dropped: the first
    is the gap eight other rows name, and nothing adds a keyword to a row.
    """
    for foe in c.trigger.targets:
        c.penalty("attack", 1, on=foe, until=When.SONT)
        c.penalty("save", 1, on=foe, until=When.SONT)


@power("f2986", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2986(c: Cast) -> None:
    """A pull whenever `p8278` bites, once a turn.

    `DamageApplied.detail` is the power that dealt it, which is the only
    event that says "damage from this row" rather than "a hit with this
    row" -- and the printed line is about applying damage. "Once per turn"
    is kept in the closure rather than in `once_per_round=`, because the
    header field counts the *row's* uses and this row is a trait that is
    used once.
    """
    me = c.me
    reach = max(c.con_mod, c.int_mod)
    spent: list[tuple[int, int | None]] = []

    def bite(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail != "p8278":
            return
        now = (c.world.round, c.world.turn)
        if now in spent:
            return
        spent.append(now)
        c.pull(reach, on=ev.target)

    c.watch(DamageApplied, bite, until=When.ENCOUNTER, on=me, label=f"{c.ref} drag")


@power("f2997", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f2997(c: Cast) -> None:
    """"The next attack roll" is `once=True`; untyped, as printed."""
    c.bonus("attack", 1, on=c.me, until=When.EONT, once=True)


@power("f1538", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(COUNTS_AS,))
def f1538(c: Cast) -> None:
    """Every attack gains the fear keyword after `p1628`. The power is a
    ref, so the whole hold is the keyword: nothing adds one to the rows a
    creature is about to use -- `c.rattling` does it for exactly one
    keyword and generalises to none."""


@power("f2983", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(COUNTS_AS,))
def f2983(c: Cast) -> None:
    """Re-aimed: the racial power is `p1448` and it is declared, so the
    name is no longer the gap. `cf:invoker-f1` asks the header fields of
    the resolved row and nothing overrides those from outside, which is
    the one thing still missing. The skill bonus is a column."""


@power("f2177", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(COUNTS_AS, "c.reshape_area()"))
def f2177(c: Cast) -> None:
    """Two clauses, neither sayable. `p1448` is a ref but nothing makes one
    row count as divine, and turning a burst into a close blast 3 changes
    the header's `reach` for one use -- `c.widen_areas` grows an area and
    does not reshape one."""


@power("f3001", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f3001(c: Cast) -> None:
    """Extra damage on a target hit by a racial reroll. `p1450` is a ref;
    what is missing is that nothing announces a roll was a reroll."""


# -- standing riders on this invoker's own attacks --------------------------


@power("f2991", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2991(c: Cast) -> None:
    """"Not adjacent to any creature" is asked per attack, because it is
    about where the enemy is standing at the moment of the shot. The
    paragon and epic steps of the bonus are out of scope."""
    def alone(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or not ctx.get("ranged", False):
            return False
        if not _divine(ctx.get("power", "")):
            return False
        return not [x for x in c.within(1, of=foe) if x != foe]

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, kind="feat", when=alone)


@power("f2999", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=NARROW_CA)
def f2999(c: Cast) -> None:
    """Combat advantage for close blasts against adjacent enemies, and
    nothing else. Both halves are conditions on the attack being made
    rather than on a moment, and `c.grants_advantage` takes no `when=` --
    so unlike f2757 and f2988 there is no firing at which the set of
    creatures could be fixed, and the whole row is the gap."""


@power("f3000", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a ranged invoker attack",
       on=Trigger(Hit, _ranged_divine_hit, "you hit somebody at range"))
def f3000(c: Cast) -> None:
    """"Against opportunity attacks" is a gate the defence context does
    carry, so all four defences take the same `when=`. The allies are
    fixed at the moment of the hit, which is what "each ally adjacent to
    the target" names."""
    foe = c.trigger.target
    for friend in c.allies():
        if not c.adjacent_to(foe, friend):
            continue
        for guarded in (AC, FORT, REF, WILL):
            c.bonus(
                guarded, 2, on=friend, until=When.SONT,
                when=lambda ctx: ctx.get("opportunity", False),
            )


@power("f2032", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a target with f2023b",
       on=Trigger(Hit, _hit_with("f2023b"), "you hit with that card"))
def f2032(c: Cast) -> None:
    """`f2023b` is another feat's granted card and a ref, so both halves
    are writable. The second half watches `Miss` on the same creature --
    "whenever the target misses with an attack roll" is about who swung,
    which is `Miss.attacker`."""
    foe = c.trigger.target
    c.slide(1, on=foe)

    def stumble(ev: Miss) -> None:
        if ev.attacker == foe:
            c.slide(1, on=foe)

    c.watch(Miss, stumble, until=When.EONT, on=c.me, label=f"{c.ref} stumble")
