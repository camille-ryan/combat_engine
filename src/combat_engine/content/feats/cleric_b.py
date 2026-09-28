"""Cleric feats, the second batch.

`cleric.py` holds the first and this one runs on the same rail: the
prerequisites name the two rows nearly every benefit rides on **by
ref**, `p1455` and `p1589`, so "when you use healing word" and "when
you use divine fortune" are ordinary `Trigger(PowerUsed, ...)` lines
rather than naming gaps.

Two things about those two rows decide most of the file.

`p1455` picks the creature it heals **inside its own body** -- it
offers a choice and the choice can be declined -- so
`PowerUsed.targets` names whoever the framework pre-selected and not
whoever actually regained hit points. Every "targets of your healing
word" row here therefore hangs off `Healed` instead, through
`_once_healed`. `Healed` is a `Decision` whose `amount` is read back
after the bus returns, which is also what makes "the target regains
additional hit points" writable at all: the rider adds to the number
before it lands rather than clawing it back afterwards.

`p1589` lays an untyped +1 to attack, spent by the first roll, and an
untyped +1 to saves. Untyped bonuses stack, so "the bonus increases to
+3" is a second, larger untyped bonus of the same shape and not a
rewrite of the first.

What is missing throughout is causation on the healing side: `Healed`
carries a source and no power, so "your **cleric healing** powers"
narrows to "anything you heal". Three rows drop that clause and say so.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    DamageApplied,
    DamageType,
    Healed,
    Hit,
    Keyword,
    PowerUsed,
    SavingThrow,
    Trigger,
    TurnEnd,
    When,
    power,
)
from combat_engine.engine.query import allies, distance_between

WORD = "p1455"
FORTUNE = "p1589"

#: `Healed` names a source and no power, so "your cleric healing
#: powers" cannot be told from any other heal you cause.
HEAL_SOURCE = ("Healed.power",)

_DEFENCES = (AC, FORT, REF, WILL)


def _i_used(ref: str):  # noqa: ANN202
    """You used that one row, named by its ref."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _once_healed(c: Cast, fn) -> None:  # noqa: ANN001
    """Answer the next creature this caster actually heals.

    `once=True` on `c.watch` reads the log to decide whether the handler
    did anything, and a handler whose whole job is to raise `ev.amount`
    announces nothing -- so it would never spend its hold. The guard is
    kept here instead.
    """
    fired: list[int] = []

    def go(ev: Any) -> None:
        if ev.source != c.me or fired:
            return
        fired.append(1)
        fn(ev)

    c.watch(Healed, go, until=When.EOT)


# -- healing word, which is p1455 in five of these prerequisites -----------


@power("f1518", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455 on an ally",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f1518(c: Cast) -> None:
    """**You** gain the temporary hit points, not the ally."""
    c.temp_hp(c.con_mod, on=c.me)


@power("f1752", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f1752(c: Cast) -> None:
    """"Until the start of your next turn", which is `SONT` and not the
    `EONT` most riders print."""

    def pay(ev: Any) -> None:
        for defence in _DEFENCES:
            c.bonus(defence, 2, on=ev.target, until=When.SONT)

    _once_healed(c, pay)


@power("f1966", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f1966(c: Cast) -> None:
    """Extra hit points counted off the recipient's own surroundings,
    so the count is taken when the heal lands rather than when the
    power is announced."""

    def pay(ev: Any) -> None:
        ev.amount += len(c.within(1, of=ev.target, side="enemy"))

    _once_healed(c, pay)


@power("f2182", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455 while bloodied",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f2182(c: Cast) -> None:
    """Bloodied is asked of the caster at the moment of use."""
    if not c.bloodied(c.me):
        return

    def pay(ev: Any) -> None:
        ev.amount += c.con_mod

    _once_healed(c, pay)


@power("f2005", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.forgo_healing()",),
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f2005(c: Cast) -> None:
    """Resistance instead of the extra hit points.

    The trade is dropped: nothing suppresses one clause of another
    row's body, so the resistance is granted and `p1455`'s own extra
    hit points are granted too. `c.half_healing` is the nearest thing
    in the tree and it is a standing penalty on a creature, not a
    forgoing of one heal.
    """
    if not c.may("grant resistance instead of the extra hit points"):
        return

    def pay(ev: Any) -> None:
        c.resist(5, DamageType.NECROTIC, on=ev.target, until=When.EONT)

    _once_healed(c, pay)


@power("f2866", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used(WORD), "you use p1455"))
def f2866(c: Cast) -> None:
    """Both halves. "Against poison" is the keywords of the row that laid
    the hold, with the burn's own type as the fallback for an ongoing
    poison laid by a row that prints no keyword.

    The ref for this one comes from the five prerequisites in the same
    list that gate on `has p1455`, not from a name.
    """

    def pay(ev: Any) -> None:
        c.bonus(FORT, 4, on=ev.target, until=When.EONT, kind="power")
        c.bonus(
            "save", 4, on=ev.target, until=When.EONT, kind="power",
            when=lambda ctx: Keyword.POISON in ctx.get("keywords", ())
            or ctx.get("dtype") is DamageType.POISON,
        )

    _once_healed(c, pay)


@power("f1547", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=HEAL_SOURCE)
def f1547(c: Cast) -> None:
    """Two standing clauses, so a trait with two watchers rather than a
    declared trigger -- a row with `on=` lays nothing until it fires.

    The healing half is dropped down to "anything you heal": the
    printed line is healing word *or a divine power that lets a target
    spend a surge*, and `Healed` names no power. `SurgeSpent` is no
    help either -- its actor is whoever spent it, with nothing saying
    whose power asked.

    The stun half reads "hit **or miss** ... and deal damage to it",
    which is one event rather than two: damage landing on a creature
    already bloodied.
    """
    extra = "1d6" if c.level < 11 else "2d6"

    def more(ev: Any) -> None:
        if ev.source == c.me:
            ev.amount += c.roll(extra) + c.cha_mod

    def stun(ev: Any) -> None:
        if ev.source == c.me and ev.target != c.me and c.bloodied(ev.target):
            c.stunned(on=c.me, until=When.EONT)

    c.watch(Healed, more, until=When.ENCOUNTER)
    c.watch(DamageApplied, stun, until=When.ENCOUNTER)


@power("f1531", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=HEAL_SOURCE)
def f1531(c: Cast) -> None:
    """Adds a held implement's enhancement bonus to what a surge
    restores.

    Re-aimed, and the old marker was wrong twice. An implement is an
    ordinary `Weapon` of the `implement` group -- that is how the whole
    tree carries one -- so `c.held(what="implement")` finds it and
    `Weapon.enhancement` is its plus. And `c.enhancement`'s own
    documented fallback is "whatever magic is held, then 1", which is
    exactly the number a feat wants, so it covers a chassis that keeps
    the symbol stowed rather than in hand.

    What is genuinely missing is the same clause `f1547` and `f1534`
    drop: `Healed` names a source and no power, so "with any of your
    cleric healing powers" widens to anything this cleric heals.
    """
    armed = [w for w in c.held(on=c.me, what="implement") if w.enhancement]
    plus = armed[0].enhancement if armed else c.enhancement

    def more(ev: Any) -> None:
        if ev.source == c.me:
            ev.amount += plus

    c.watch(Healed, more, until=When.ENCOUNTER)


@power("f1534", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=HEAL_SOURCE,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _i_used("p2485"), "you use that racial power"))
def f1534(c: Cast) -> None:
    """A window rather than a single heal: every heal until the end of
    the next turn pays more, which is why this is a watcher on a
    duration and not the one-shot the other healing word riders use."""

    def more(ev: Any) -> None:
        if ev.source == c.me:
            ev.amount += c.str_mod

    c.watch(Healed, more, until=When.EONT)


@power("f2912", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("TempHP.power",))
def f2912(c: Cast) -> None:
    """Raises every heal by however many temporary hit points a named
    racial trait paid. The trait is a ref and `Bloodied` names its own
    actor, so both ends of the trigger are there -- what is missing is
    the number: `TempHP` carries a source and an amount and no power,
    so temporary hit points from that trait cannot be told from any
    other pool."""


@power("f1553", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SavingThrow.power",))
def f1553(c: Cast) -> None:
    """A bonus to a saving throw **your power granted**. `SavingThrow`
    announces an actor, what is being shaken off and the roll, and
    nothing about who asked for it -- so a standing +1 would pay on
    every save an ally ever makes."""


# -- divine fortune, which is p1589 ----------------------------------------


@power("f1526", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1589",
       on=Trigger(PowerUsed, _i_used(FORTUNE), "you use p1589"))
def f1526(c: Cast) -> None:
    """The same pair of bonuses `p1589` lays on the cleric, mirrored on
    one ally: untyped, attack spent by the first roll, save standing.
    Which ally is a choice the scorer cannot weigh, so the nearest one
    is taken."""
    near = [
        a for a in allies(c.world, c.me)
        if distance_between(c.world, c.me, a) <= 5
    ]
    if not near:
        return
    who = min(near, key=lambda a: distance_between(c.world, c.me, a))
    c.bonus("attack", 1, on=who, until=When.EONT, once=True)
    c.bonus("save", 1, on=who, until=When.EONT)


@power("f1963", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1589",
       on=Trigger(PowerUsed, _i_used(FORTUNE), "you use p1589"))
def f1963(c: Cast) -> None:
    """"The bonus increases to +3" written as a second +2 rather than a
    rewrite. `p1589`'s +1 is untyped and untyped bonuses stack, so the
    two come to the printed +3; a same-kind +3 would have replaced it
    and come to +3 as well, but only by accident of the larger winning."""
    c.bonus("attack", 2, on=c.me, until=When.EONT, once=True)
    c.bonus("save", 2, on=c.me, until=When.EONT)


@power("f2752", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1589",
       on=Trigger(PowerUsed, _i_used(FORTUNE), "you use p1589"))
def f2752(c: Cast) -> None:
    c.temp_hp(c.cha_mod, on=c.me)
    for friend in c.within(1, side="team"):
        c.temp_hp(c.cha_mod, on=friend)


@power("f2007", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1589",
       on=Trigger(PowerUsed, _i_used(FORTUNE), "you use p1589"))
def f2007(c: Cast) -> None:
    """"Benefiting from divine fortune" is read as the window the
    bonus is live for: `p1589`'s attack half is spent by the first roll
    and its save half runs to the end of the next turn, so the first
    hit or successful save inside that window is the one the printed
    line means. Nothing announces that a particular bonus was consumed,
    and waiting for such an announcement would leave the row inert."""
    paid: list[int] = []

    def pay() -> None:
        if paid:
            return
        paid.append(1)
        for defence in _DEFENCES:
            c.bonus(defence, 2, on=c.me, until=When.EONT)

    def on_hit(ev: Any) -> None:
        if ev.attacker == c.me:
            pay()

    def on_save(ev: Any) -> None:
        if ev.actor == c.me and ev.saved:
            pay()

    c.watch(Hit, on_hit, until=When.EONT)
    c.watch(SavingThrow, on_save, until=When.EONT)


@power("f2008", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1589",
       on=Trigger(PowerUsed, _i_used(FORTUNE), "you use p1589"))
def f2008(c: Cast) -> None:
    """Same window as f2007. "Your Constitution or Dexterity modifier"
    is a choice with one sensible answer, so the larger is taken."""
    paid: list[int] = []

    def on_hit(ev: Any) -> None:
        if ev.attacker != c.me or paid:
            return
        paid.append(1)
        c.flat(max(c.con_mod, c.dex_mod), dtype=DamageType.NECROTIC,
               on=ev.target)

    c.watch(Hit, on_hit, until=When.EONT)


# -- the rest --------------------------------------------------------------


@power("f1960", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f1960(c: Cast) -> None:
    """Shield and weapon proficiency are build-time permissions."""


@power("f1962", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("feat.associated_powers",))
def f1962(c: Cast) -> None:
    """An attack bonus with the at-will powers a domain is associated
    with. The class feature it rides on is a ref, but nothing records
    which domain a character took or which rows that domain names --
    the same list `f2071` wanted."""


@power("f1964", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1964(c: Cast) -> None:
    """A skill bonus and a death-save bonus.

    `turns._death_saves` hard-codes `bonus=0` and never asks
    `total("save")`, so `c.bonus("save", ...)` would be laid and never
    read. But the `SavingThrow` it emits is a `Decision` read back for
    its `saved` flag, which is the seam: the roll is re-decided here
    with the +5 in it. Distance is asked when the save is rolled, not
    when the trait is armed, because both creatures move.
    """
    c.bonus("skill:heal", 2, on=c.me, until=When.ENCOUNTER)

    def boost(ev: Any) -> None:
        if ev.against != "death" or ev.saved:
            return
        if ev.actor not in allies(c.world, c.me):
            return
        if distance_between(c.world, c.me, ev.actor) > 5:
            return
        ev.saved = ev.natural + ev.bonus + 5 >= 10

    c.watch(SavingThrow, boost, until=When.ENCOUNTER)


@power("f1965", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1965(c: Cast) -> None:
    """"You hit with an attack that doesn't deal damage" and "you
    didn't deal any damage on your turn" are the same question asked
    once at the end of the turn: did a blow land, and did nothing take
    damage from me. So the turn is watched rather than the attack, and
    the flags reset as they are read."""
    amount = 2 + (c.level >= 11) + (c.level >= 21)
    seen = {"hit": False, "damage": False}

    def on_hit(ev: Any) -> None:
        if ev.attacker == c.me:
            seen["hit"] = True

    def on_damage(ev: Any) -> None:
        if ev.source == c.me and ev.target != c.me:
            seen["damage"] = True

    def on_turn_end(ev: Any) -> None:
        if ev.actor != c.me:
            return
        if seen["hit"] and not seen["damage"]:
            c.temp_hp(amount, on=c.me)
        seen["hit"] = seen["damage"] = False

    c.watch(Hit, on_hit, until=When.ENCOUNTER)
    c.watch(DamageApplied, on_damage, until=When.ENCOUNTER)
    c.watch(TurnEnd, on_turn_end, until=When.ENCOUNTER)
