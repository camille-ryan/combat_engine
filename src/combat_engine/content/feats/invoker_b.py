"""Invoker feats, the second batch.

`invoker.py` holds the first. Almost every row here hangs off the class's
one big fork -- which covenant was taken -- and that fork is askable:
`chargen.BUILDS["invoker"]` carries `wrath`, `preservation` and
`malediction`, so `c.build(...)` answers and three rows branch on it.

Two shapes make up most of the list.

**"A divine encounter or daily attack power"** is writable and is the
spine of eight rows: `Keyword.DIVINE` plus `p.usage` plus `p.is_attack`,
read off the resolved row exactly the way `cf:invoker-covenant` reads it.
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
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
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
from combat_engine.engine.events import PowerResolved
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


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


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
    covenant manifestation" is dropped: `cf:invoker-covenant` arms its own
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


@power("f1506", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1506(c: Cast) -> None:
    """Intelligence on the damage of the attack a covenant reaction helped.
    The spec's `m5994a3` is a monster ability the importer's name index
    landed on, not this feature -- so the feature is still an unresolved
    name."""


@power("f1521", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1521(c: Cast) -> None:
    """Five elemental variants of a bonus to the ally the same covenant
    reaction protected. Same unresolved name as f1506; `c.element` would
    pick the leg once there were something to hang it on."""


@power("f1525", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1525(c: Cast) -> None:
    """A teleport for the ally that covenant reaction protected. Same
    unresolved name as f1506."""


@power("f1549", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1549(c: Cast) -> None:
    """Concealment for the same ally. Same unresolved name as f1506."""


@power("f1748", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1748(c: Cast) -> None:
    """Combat advantage when an attack roll that covenant reaction boosted
    lands. Named in prose, and the boost it asks about is chosen inside the
    feature's own body."""


@power("f2995", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2995(c: Cast) -> None:
    """Insubstantial for the ally that covenant reaction answered for.
    Named in prose with no ref."""


@power("f2996", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2996(c: Cast) -> None:
    """A slide and a mark cleared off the same ally. Same naming gap as
    f2995; `c.cure(Condition.MARKED)` would say the second half."""


@power("f1510", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1510(c: Cast) -> None:
    """Combat advantage for the next ally against an elemental creature the
    covenant's channelled invocation hit. `c.is_kind("elemental")` and
    `c.grants_advantage(to="ally")` both say their half -- the invocation
    is named in prose, and only f2985's prerequisite gives a ref for it."""


@power("f2006", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2006(c: Cast) -> None:
    """A push whenever a creature under that same channelled invocation is
    hit by a fear, cold or necrotic attack. Same naming gap as f1510."""


@power("f1562", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1562(c: Cast) -> None:
    """Wisdom on the damage of the wrath covenant's reaction against a
    larger enemy. `c.size_of` is there; the reaction is named in prose and
    no prerequisite gives its ref."""


@power("f1563", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1563(c: Cast) -> None:
    """Prone after that reaction's push. Same naming gap as f1562, and the
    push happens inside the feature's own body."""


@power("f2003", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2003(c: Cast) -> None:
    """Extra cold damage and an immobilise on undead the same reaction
    hits. Same naming gap as f1562."""


@power("f2874", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2874(c: Cast) -> None:
    """Widens what sets that reaction off, from being hit yourself to an
    ally within 5 squares being hit. Its trigger is written inside the
    feature, which has no ref -- so there is nothing to widen."""


@power("f2987", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("p2473",))
def f2987(c: Cast) -> None:
    """Concealment for an ally when the covenant manifestation goes off
    while you stand in your own racial zone. The manifestation is
    `cf:invoker-covenant` and its moment is readable -- `p2473` is not in
    the tree, so there is no zone to ask about and `c.my_zones` cannot tell
    which of several it would be."""


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
       reach=PERSONAL, target=SELF, todo=(RACIAL[0], COUNTS_AS))
def f1538(c: Cast) -> None:
    """Every attack gains the fear keyword after a racial power. Two gaps:
    the power is named in prose, and nothing adds a keyword to the rows a
    creature is about to use -- `c.rattling` does it for exactly one
    keyword and generalises to none."""


@power("f2983", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(RACIAL[0], COUNTS_AS))
def f2983(c: Cast) -> None:
    """Makes a racial power count as a divine encounter attack so the
    covenant manifestation reads it. The power is named in prose, and
    `cf:invoker-covenant` asks the header fields of the resolved row --
    nothing overrides those from outside. The skill bonus is a column."""


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
