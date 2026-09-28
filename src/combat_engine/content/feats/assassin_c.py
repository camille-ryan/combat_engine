"""Assassin feats, the third batch: the rows that hang off a named power.

Nearly every card here reads "when you use <a row the spec gives by ref>",
so `PowerUsed` does most of the work. It is announced **before** the body
runs, and that decides how each row is written: a rider that adds to what
the power is about to do is laid straight away, and one that reads where
the power *left* you -- `f2831`, `f2938` -- hangs a `c.watch` on the
consequence instead.

`usage=AT_WILL` throughout. None of these cards prints a once-per-encounter
limit, and `triggers._answers` asks `usable` every time it offers a row, so
`ENCOUNTER` would quietly turn "whenever you use it" into "once a fight".

**Invoking the shrouds** was the gap four rows here carried, and it is
closed. `p9400` arms the invoking as a pair of watchers on the assassin's
own `Hit` and `Miss`, so the moment *is* announced -- it is the attack
event itself. A listener in the `Window.BEFORE` half of that event runs
ahead of `p9400`'s own, which is where the count is still intact; the
payout it rolls comes through as a `DamageRolled` whose `detail` is
`p9400`, because `c.flat` stamps the rolling row's ref. Between the two,
"when you invoke" and "the damage from p9400" are both askable.

**A power's printed distance** is the one that remains. "Teleport your
Dexterity modifier instead", "add 2 squares to your teleport": the reach a
row moves you is header data the menu reads before anything runs, and
`c.extend_move()` is the symbol two other classes already name for it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    PowerUsed,
    Trigger,
    When,
    Window,
    power,
    targets_me,
)
from combat_engine.engine.components import Shrouds
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    DamageRolled,
    Miss,
    MoveEnd,
    OpportunityWindow,
    SkillCheck,
    TempHP,
)

#: The row whose body invokes the shrouds and rolls what they are worth.
SHROUDS = "p9400"
#: How far a named row moves you is header data, read before the body.
DISTANCE = ("c.extend_move()",)
#: A row's printed Requirement, waived for one use. `Power.requires` is
#: asked by `dsl.usable` and nothing standing on the creature relaxes it.
REQUIREMENT = ("c.ignore_requirement(ref)",)


def _used(ref: str):  # noqa: ANN202
    """That named row, used by me."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _in_zone(c: Cast, ref: str) -> bool:
    """Is the caster standing in a zone its own named row laid?

    `c.my_zones` gives the ids and nothing gives membership, so the
    squares are asked directly -- a zone keeps them as a frozenset and
    `c.here` is the one square that has to be in it.
    """
    for _zid, zone in c.world.zones.all():
        if zone.owner == c.me and ref in (zone.label or "") and c.here in zone.squares:
            return True
    return False


def _in_form(c: Cast, ref: str) -> bool:
    """Is that row's effect still standing on the caster?

    There is no `c.running(ref)`; every effect a row lays is labelled with
    the ref that laid it, so the live list is the register. The same read
    `assassin_b._holding_form` does, kept local rather than imported out
    of another content file.
    """
    return any(eff.label.startswith(ref) for eff in c.world.effects.of(c.me))


def _per_shroud(c: Cast, foe: int, until: When) -> None:
    """"1 extra damage for each shroud on it", against one creature.

    The count moves during a fight, so it cannot be baked into a single
    number: each rung is gated on the count having reached it and carries
    its own `kind`, so the four add rather than the largest winning.
    """
    for count in (1, 2, 3, 4):
        c.bonus(
            "damage", 1, on=c.me, until=until, kind=f"{c.ref}:{count}",
            when=lambda ctx, n=count: (
                ctx.get("target") == foe and c.shrouds(foe) >= n
            ),
        )


# -- riders on a named power, written straight ------------------------------


@power("f2823", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.shift_becomes_teleport()",),
       trigger="you use p7443",
       on=Trigger(PowerUsed, _used("p7443"), "you use that power"))
def f2823(c: Cast) -> None:
    """The damage half is ordinary; the movement half is dropped.

    "You teleport instead of shift" rewrites what another row's own move
    is, and a shift is spent inside that row's body from its own header.
    Laying a teleport of my own here would be a second move rather than a
    replacement, which is further than the card takes anybody.
    """
    for foe in c.trigger.targets:
        _per_shroud(c, foe, When.EONT)


@power("f2824", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7546 and succeed on the check",
       on=Trigger(PowerUsed, _used("p7546"), "you use that power"))
def f2824(c: Cast) -> None:
    """The check is rolled inside p7546's own body, and `PowerUsed` fires
    before that body -- so the success cannot be read here. It is waited
    for instead, and `SkillCheck` carries `success` finished.

    "Even if you have already used it on the target this turn" is nothing
    to lift: `c.shroud` keeps a victim and a count and has never enforced
    a once-a-turn limit, so the permission is already the engine's rule.
    """
    me, foes = c.me, list(c.trigger.targets)
    done: list[bool] = []

    def on_check(ev: SkillCheck) -> None:
        if ev.actor != me or done or ev.skill != "bluff" or not ev.success:
            return
        done.append(True)
        for foe in foes:
            c.shroud(on=foe)

    c.watch(SkillCheck, on_check, until=When.EOT, on=me)


@power("f2827", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7442 against a shrouded enemy",
       on=Trigger(PowerUsed, _used("p7442"), "you use that power"))
def f2827(c: Cast) -> None:
    """`PowerUsed` firing before the body is what makes this writable: the
    advantage is standing by the time p7442 rolls its attack. `once=True`
    spends it on that one swing, which is the printed scope."""
    for foe in c.trigger.targets:
        if c.shrouds(foe):
            c.grants_advantage(on=foe, until=When.EOT, once=True)


@power("f2831", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=DISTANCE,
       trigger="you use p9401 inside your p2473",
       on=Trigger(PowerUsed, _used("p9401"), "you use that teleport"))
def f2831(c: Cast) -> None:
    """Combat advantage from whoever you land beside.

    The distance is dropped: "instead, teleport a number of squares equal
    to your Dexterity modifier" replaces another row's own move, and a
    teleport of my own laid here would be a second one on top of it.

    Where you land is read off `MoveEnd` rather than here, because
    `PowerUsed` is announced before the body and nothing has moved yet --
    which is precisely the adjacency the card asks about.

    `p2473` lays its zone with no `label=`, and `Cast.zone` defaults one
    to the casting row's own ref -- so the string `_in_zone` matches on
    is that ref and nothing else.
    """
    if not _in_zone(c, "p2473"):
        return
    me = c.me
    done: list[bool] = []

    def on_land(ev: MoveEnd) -> None:
        if ev.actor != me or done:
            return
        done.append(True)
        for foe in c.enemies():
            if c.adjacent(to=foe):
                c.grants_advantage(on=foe, until=When.EONT)
                return

    c.watch(MoveEnd, on_land, until=When.EOT, on=me)


@power("f2832", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7548",
       on=Trigger(PowerUsed, _used("p7548"), "you use that power"))
def f2832(c: Cast) -> None:
    """Paid at once rather than as a damage modifier: the card gives the
    enemy damage for using the power, not a bonus to a later roll.

    Floored at zero. A modifier can be negative and `c.flat` does not
    mind, so a multiclass assassin with a poor Charisma would otherwise
    heal the enemy the sentence is meant to hurt.
    """
    for foe in c.trigger.targets:
        c.flat(
            max(0, c.cha_mod + c.shrouds(foe)),
            dtype=DamageType.PSYCHIC, on=foe,
        )


@power("f2833", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used("p2339"), "you use that power"))
def f2833(c: Cast) -> None:
    """"Any or all" -- every target is inside the printed choice and none
    of them would refuse concealment, so all of them get it."""
    for who in c.trigger.targets:
        c.conceal(on=who, until=When.SONT)


@power("f2932", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f2932(c: Cast) -> None:
    """The caster is concealed once, outside the loop: `side="ally"` leaves
    it out of the pool, and two holds of the same label on one creature
    would be two things to end."""
    c.conceal(on=c.me, until=When.EONT)
    for ally in c.within(5, of=c.me, side="ally"):
        if ally != c.me:
            c.conceal(on=ally, until=When.EONT)


@power("f2933", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=REQUIREMENT,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f2933(c: Cast) -> None:
    """The cheaper action is the whole first sentence and `c.recast` is
    exactly it. The second -- the triggering creature counting for p9401's
    own Requirement -- is dropped: that gate is asked by `dsl.usable` off
    the header and nothing standing on a creature relaxes one."""
    c.recast("p9401", action=ActionType.FREE, per_turn=1, until=When.EOT)


@power("f2934", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f2934(c: Cast) -> None:
    """Moving the shrouds, count intact.

    `c.shroud` would be wrong here: shrouds follow one victim at a time,
    so naming a new one there resets the count to zero and lays a single
    fresh shroud. The component is a victim and a number, and "move any
    shrouds upon it" is the victim changing -- which is the one operation
    the verbs do not offer, so it is done on the component directly.
    """
    held = c.world.get(c.me, Shrouds)
    if held is None or not held.count:
        return
    for victim in c.trigger.targets:
        if held.on != victim:
            continue
        near = [foe for foe in c.within(10, of=victim, side="enemy") if foe != victim]
        if near:
            held.on = c.choose(near, f"{c.ref}: move the shrouds to") or held.on
        return


@power("f2938", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f2938(c: Cast) -> None:
    """A miss that still costs the target something.

    `c.struck_with` hands back the weapon the triggering attack was made
    with, and an implement's base item is its group -- so "with a ki
    focus" is a group question and the enhancement is read off the same
    object rather than off whatever is in hand now.

    The latch is a list rather than `c.watch(once=True)`: that spends
    itself on the first `Miss` of anybody's, and a miss by somebody else
    is not this sentence.
    """
    me = c.me
    done: list[bool] = []

    def on_miss(ev: Miss) -> None:
        if ev.attacker != me or done:
            return
        weapon = c.struck_with(ev)
        if weapon is None or weapon.group != "ki focus":
            return
        done.append(True)
        c.flat(2 * weapon.enhancement, dtype=DamageType.NECROTIC, on=ev.target)

    c.watch(Miss, on_miss, until=When.EONT, on=me)


@power("f2939", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f2939(c: Cast) -> None:
    """`c.invisible` with no `to=` is invisible to everybody, which is what
    "become invisible" means; the duration is the printed one rather than
    the method's default."""
    c.invisible(on=c.me, until=When.EONT)


@power("f3077", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an attack damages you while p9402 holds",
       on=Trigger(Hit, targets_me, "an attack hits you"))
def f3077(c: Cast) -> None:
    """"After the attack is resolved" is why this is `c.recast` rather than
    a use here and now: the permission stands to the end of the turn and
    the assassin spends it when the blow has finished landing."""
    if _in_form(c, "p9402"):
        c.recast("p9401", action=ActionType.FREE, per_turn=1, until=When.EOT)


@power("f3079", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me
       ), "you drop an enemy"))
def f3079(c: Cast) -> None:
    """`Dropped.source` is who struck the killing blow; `actor` is the
    creature that fell, and reading that one would fire this on the
    assassin's own death instead."""
    c.recast("p9401", action=ActionType.FREE, per_turn=1, until=When.EOT)


# -- standing modifiers -----------------------------------------------------


@power("f2919", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2919(c: Cast) -> None:
    """`c.ignore_cover` is one sentence for both: `resolve.attack` takes
    the larger of cover and concealment and then asks `cover_waived` with
    the attack context, so the gate is the target being bloodied.

    Not a flat +2 handed back. The attack context carries neither `cover`
    nor `concealment`, so a modifier gated on those keys is silently false
    -- which is what the waiver exists to avoid.
    """
    c.ignore_cover(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None and c.bloodied(ctx["target"])
        ),
    )


# -- the invoking ----------------------------------------------------------


def _invoked_on_a_miss(c: Cast, fn) -> None:  # noqa: ANN001
    """Arm `fn(ev)` for a miss of mine that invokes the shrouds.

    `Window.BEFORE` is the whole trick. `p9400` hangs its own invoking on
    the ordinary (`AFTER`) half of the same `Miss`, and the count is gone
    by the time that has run -- so a rider asking "how many did you
    invoke" has to ask in the interrupt window, where nothing has been
    cashed yet. Insertion order cannot be relied on for it: `p9400` arms
    itself mid-fight and a trait arms at the start, so an `AFTER`
    listener here would run *before* the invoking rather than after it.
    """
    me = c.me

    def on_miss(ev: Miss) -> None:
        if ev.attacker == me and c.shrouds(ev.target):
            fn(ev)

    c.watch(Miss, on_miss, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


@power("f2828", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2828(c: Cast) -> None:
    """A miss that invoked two or more shrouds pays the ranger's rider
    anyway.

    `c.quarry_damage` is the dice that feature rolls and
    `c.total("cf:ranger-f1 damage")` the modifier a build feature may have
    raised it by -- the pair `features.extra_damage` itself pays with, so
    the two cannot disagree. `detail=` names the feature rather than this
    feat, because the printed line is that feature's damage arriving by
    another road.
    """
    def pay(ev: Miss) -> None:
        if c.shrouds(ev.target) >= 2:
            c.damage(c.quarry_damage(), c.total("cf:ranger-f1 damage"),
                     on=ev.target, detail="cf:ranger-f1")

    _invoked_on_a_miss(c, pay)


@power("f2829", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2829(c: Cast) -> None:
    """The rogue's side of f2828.

    `c.had_advantage` reads the grant off the attack that missed rather
    than asking the board again -- a one-shot grant has already been
    spent by the time the roll is over, so the second question comes back
    false exactly when the card means yes.
    """
    def pay(ev: Miss) -> None:
        if c.shrouds(ev.target) >= 2 and c.had_advantage(ev):
            c.damage(c.sneak_damage(), c.total("cf:rogue-scoundrel-f4 damage"),
                     on=ev.target, detail="cf:rogue-scoundrel-f4")

    _invoked_on_a_miss(c, pay)


@power("f2922", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2922(c: Cast) -> None:
    """Turns the shroud damage radiant when a divine power invoked it.

    Not `c.deals`, which retypes everything the creature throws and takes
    no gate: only the one blow `p9400` rolls is meant. That blow announces
    itself as a `DamageRolled` whose `detail` is `p9400`, and the type on
    that event is writable and is what resistance and the `DamageApplied`
    below it both read.

    Which power invoked them is latched off the attack rather than read
    off the damage: the damage context carries the *rolling* row, which is
    always `p9400`, and the attack that set it off is only nameable while
    its own event is in the air.
    """
    me = c.me
    divine: list[bool] = [False]

    def on_swing(ev: Any) -> None:
        if ev.attacker != me:
            return
        row = get(ev.power)
        divine[0] = row is not None and Keyword.DIVINE in row.keywords

    def retype(ev: DamageRolled) -> None:
        if divine[0] and ev.source == me and ev.detail == SHROUDS:
            ev.dtype = DamageType.RADIANT

    for outcome in (Hit, Miss):
        c.watch(outcome, on_swing, until=When.ENCOUNTER, on=me,
                window=Window.BEFORE, label=c.ref)
    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2937", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2937(c: Cast) -> None:
    """Keeps a shroud back on a miss against one sort of creature.

    Written as a shroud handed over rather than as damage added, because
    `p9400`'s miss line is `count - 1` and then `count` dice *and* `count`
    times the per-tier number: one extra die is the wrong answer above
    heroic, and at a count of one there is no `DamageRolled` to amend at
    all. Lending one back in the interrupt window makes the subtraction
    land on the number the card says it should.

    Above `p9400`'s own cap deliberately -- the loan lives for the length
    of one event and `c.spend_shrouds` clears the lot a line later.
    """
    def lend(ev: Miss) -> None:
        if {"undead", "shadow"} & c.kinds_of(ev.target):
            c.shroud(on=ev.target, cap=c.shrouds(ev.target) + 1)

    _invoked_on_a_miss(c, lend)


# -- a power's printed distance ---------------------------------------------


@power("f2921", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=DISTANCE)
def f2921(c: Cast) -> None:
    """Two squares further on any teleport that ends beside the p3069
    target. `c.teleport` takes a distance from its caller and there is no
    standing modifier a move of any kind reads."""


@power("f2935", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=DISTANCE)
def f2935(c: Cast) -> None:
    """A square further on p9401, and it accumulates across a fight. Same
    gap as f2921, and it is the half f2831 drops."""


# -- the rest ---------------------------------------------------------------


@power("f2830", level=1, cls="", usage=AT_WILL, action=ActionType.FREE,
       reach=PERSONAL, target=SELF)
def f2830(c: Cast) -> None:
    """Spends one named row to get another back -- the same shape
    assassin_b's f2815 carries, and written the same way: the payout
    only happens if `c.expend_row` found a use to take."""
    if c.expend_row("p2485"):
        c.restore_use("p9402", on=c.me)


@power("f2837", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2837(c: Cast) -> None:
    """No opportunity attacks from a shrouded creature, and only against
    one shape of attack.

    `c.no_provoke` takes the creature but no `when=`, so the veto is
    written out: `OpportunityWindow.why` records *what* opened the
    window, and `dsl` spells a ranged power's as "<ref> is a ranged
    power". Reading the ref back off it is how "your ranged sorcerer
    attacks" is narrowed to the class -- walking away from the creature
    still provokes, which is the half a bare waiver would have thrown in.
    """
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker != me or not c.shrouds(ev.actor):
            return
        if not ev.why.endswith(" is a ranged power"):
            return
        row = get(ev.why.split(" ", 1)[0])
        if row is not None and row.cls == "sorcerer":
            ev.cancel(c.ref)

    c.watch(OpportunityWindow, veto, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


@power("f2920", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:holy-symbol",))
def f2920(c: Cast) -> None:
    """The whole benefit is the header field, as f2814's rods are.

    Not the gap assassin_b's f2812 drops. That one has to rewrite an
    object already in hand; this one only has to put one there, and
    `chargen` reads `proficiency=` when the character is built. A holy
    symbol's `group` is `implement` in this engine, so being handed one
    *is* being able to cast with one and there is nothing for the body to
    say.
    """


@power("f2931", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REQUIREMENT)
def f2931(c: Cast) -> None:
    """Waives p9401's own Requirement while bloodied. `c.bloodied` is the
    easy half; the gate is `Power.requires`, asked by `dsl.usable` off the
    header, and nothing standing on the creature relaxes one."""


@power("f2936", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2936(c: Cast) -> None:
    """Raises the temporary hit points `cf:assassin-f1` hands out, and
    doubles the raise against two creature types.

    `TempHP` still names neither the row that paid nor the creature whose
    being hit caused it, so both are carried across from the hit instead:
    the feature's whole condition is "you hit somebody who is not
    bloodied", which is what the latch below holds, and the creature it
    holds is the one the second sentence asks about.

    Re-applied rather than amended. `resolve.temp_hp` writes the pool and
    *then* announces, so an interrupt on the announcement would change a
    number already stored; a second, larger call is the one operation
    that moves it, and temporary hit points not stacking is what makes
    that a raise rather than an addition.

    The narrow way it can be wrong: another source paying the assassin
    temporary hit points inside the same hit would be raised too. Nothing
    in the class does, and the alternative is no row at all.
    """
    me = c.me
    struck: list[int] = []

    def on_hit(ev: Hit) -> None:
        # Reset first: a hit that qualifies and pays nothing -- the pool
        # is already the larger -- must not leave the latch standing for
        # whatever the next hit hands over.
        struck.clear()
        if ev.attacker == me and ev.target != me and not c.bloodied(on=ev.target):
            struck.append(ev.target)

    def raise_it(ev: TempHP) -> None:
        if ev.source != me or ev.target != me or not struck:
            return
        victim = struck.pop()
        bump = 2 if {"undead", "shadow"} & c.kinds_of(victim) else 1
        c.temp_hp(ev.amount + bump, on=me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)
    c.watch(TempHP, raise_it, until=When.ENCOUNTER, on=me, label=c.ref)
