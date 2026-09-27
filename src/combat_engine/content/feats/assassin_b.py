"""Assassin feats, the second batch: the shroud and the racial powers.

Two things decide almost every row here.

**The shroud is fully modelled and fully nameable.** `p9400` is in most
of these prerequisites, `c.shroud` lays one, `c.shrouds` counts them, and
`p9402` -- shade form -- is named by ref too. So anything that is purely
"another shroud", "extra damage per shroud", "resist per shroud" is an
ordinary row.

**Nearly every racial power here is nameable.** `p8278`, `p2482`,
`p2473`, `p1831`, `p7441`, `m4421a6`, `p1448`, `p377`, `p1452`, `p1449`,
`p2480`, `p6189` and `p7546` all arrive as refs, so a rider on one is an
ordinary `PowerUsed` or `Hit` trigger. Three rows are left naming their
power in prose -- a racial *trait*'s borrowed power, the shroud power
itself and one encounter power -- and those keep `c.on_racial_power()`,
the symbol the rogue's `f767` named.

Several of the newly-named ones are still refused, but for a different
reason each: a row cannot *use* another row (`c.use_power()`), cannot
spend one to pay a cost (`c.expend_row()`), cannot lengthen the move a
named row makes (`c.extend_move()`), and cannot reach back from a use to
the roll that use was answering (`c.triggering_of()`, which `general_o`'s
f3112 named against this same racial power).

The one genuinely new gap is **invoking** the shrouds as against merely
carrying them. `c.shroud` and `c.shrouds` say how many are on a creature;
nothing announces the moment they are cashed in, and six rows turn on
exactly that moment. `c.on_invoke_shrouds()`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    SecondWind,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import SkillCheck

#: Nothing announces the moment the shrouds are cashed in, as against
#: merely counted. Six rows here turn on that moment and nothing else.
INVOKE = ("c.on_invoke_shrouds()",)
#: A racial power named in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)

#: The class's own shroud power and its shade form, both named by ref in
#: these feats' own prerequisites.
SHROUD = "p9400"
SHADE = "p9402"


def _holding_form(c: Cast, ref: str) -> bool:
    """Is that row's effect still standing on the caster?

    There is no `c.running(ref)`. Every effect a row lays is labelled
    with the ref that laid it -- `c.effect` and `c.bonus` both do it --
    so the live list is the register, read directly rather than through
    a verb that does not exist.
    """
    return any(
        eff.label.startswith(ref) for eff in c.world.effects.of(c.me)
    )


def _keyworded(kw: Keyword):  # noqa: ANN202
    """A hit of mine with a power carrying that keyword."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        p = get(ev.power)
        return ev.attacker == me and p is not None and kw in p.keywords

    return when


def _missed_with(kw: Keyword):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        p = get(ev.power)
        return ev.attacker == me and p is not None and kw in p.keywords

    return when


def _used(ref: str):  # noqa: ANN202
    """That named row, used by me. `PowerUsed` fires **before** the body,
    so a rider declared here runs first -- which is right for the rows
    that add to what the power is about to do and wrong for the ones
    that read its outcome. Each caller says which it is."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hit_with(ref: str):  # noqa: ANN202
    """That named row landing a blow of mine. `Hit` carries `attacker`,
    `target`, `power` and `critical`; `charge` rides on it as a plain
    attribute, which is why the callers that want it use `getattr`."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _my_illusion_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.ILLUSION in p.keywords
        and p.reach.kind == "melee"
    )


def _my_illusion_encounter(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine import DAILY

    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.ILLUSION in p.keywords
        and p.usage in (ENCOUNTER, DAILY)
        and p.is_attack
    )


# -- the shroud, which is entirely writable ---------------------------------


@power("f1798", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your shroud power",
       on=Trigger(PowerUsed, _used(SHROUD), "you lay a shroud"))
def f1798(c: Cast) -> None:
    """A second shroud, once a fight.

    `PowerUsed` fires before the body, so the shroud this is doubling has
    not landed yet -- which does not matter, because `c.shroud` caps at
    the printed four either way and the order the two arrive in is not
    observable.

    `usage=ENCOUNTER` is the printed "once per encounter"; the body
    counts nothing itself.

    `PowerUsed.targets` is a *list*, not a `target`. Reading the
    singular through `getattr` would have made this row silently do
    nothing.
    """
    for foe in c.trigger.targets:
        c.shroud(on=foe)


@power("f1796", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1796(c: Cast) -> None:
    """"Creatures you are hidden from are not aware of your shrouds."
    Awareness is not modelled at all -- no creature on a board ever acts
    on knowing a shroud is there, so there is nothing for this to
    change. Deliberately inert rather than unwritten."""


@power("f2232", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2232(c: Cast) -> None:
    """Resistance that scales with how many shrouds the attacker carries.

    `c.resist` takes a `when=`, so the gate is asked per blow rather than
    latched -- which it must be, because shrouds go on and come off
    during a fight. The amount cannot vary the same way, so it is laid
    as four separate rungs, each gated on the count reaching it, and
    `Mods.total` keeps only the largest of a same-kind bonus.
    """
    me = c.me
    for count in (1, 2, 3, 4):
        c.resist(
            count, on=me, until=When.ENCOUNTER,
            when=lambda ctx, n=count: (
                ctx.get("attacker") is not None
                and c.shrouds(ctx["attacker"]) >= n
            ),
        )


@power("f2231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2231(c: Cast) -> None:
    """Cancels the cover and concealment penalties against a shrouded
    enemy.

    **`cover` and `concealment` are not keys the attack context has.**
    `resolve.attack` builds it with `attacker, target, power, advantage,
    opportunity, charge, action_point, ranged, branch, hand` -- so a
    gate reading either was silently false and this waiver never once
    applied. `c.ignore_cover` is the verb, and it writes into the
    `ignore_cover` modifier that `query.cover_waived` actually reads.
    """
    me = c.me
    c.ignore_cover(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.shrouds(ctx["target"]) >= 1
        ),
    )


@power("f2230", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.on_invoke_shrouds()",),
       trigger="you drop a creature carrying your shrouds",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me
       ), "you drop an enemy"))
def f2230(c: Cast) -> None:
    """Temporary hit points scaled by the shrouds on whatever just fell.

    The count is read before anything clears it, because the creature is
    down and its shrouds go with it. The teleport half is dropped: it is
    gated on having *invoked* the shrouds on that blow, and nothing
    announces the invoking.
    """
    # `Dropped.actor` is the creature that fell. There is no `target` on
    # this event, and reading one through `getattr` would have made the
    # row silently do nothing -- which is the failure shape this project
    # is built to hunt, so it is named here rather than left to be found.
    victim = c.trigger.actor
    c.temp_hp(5 + c.shrouds(victim), on=c.me)


# -- poison, fear and illusion: keywords the engine has ---------------------


@power("f1800", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1800(c: Cast) -> None:
    """"+2 at 1st, +3 at 11th, +4 at 21st" is the standard tier ladder, so
    it is read off the character's level rather than written as three
    rows."""
    me = c.me
    step = 2 + (c.level >= 11) + (c.level >= 21)
    c.bonus(
        "damage", step, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.FEAR in p.keywords
        ),
    )


@power("f1810", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1810(c: Cast) -> None:
    """A bonus to *poison damage*, which is the damage type rather than
    the keyword -- and the damage context now carries `dtype`, which is
    the whole reason this row is writable."""
    me = c.me
    step = 2 + (c.level >= 11) + (c.level >= 21)
    c.bonus(
        "damage", step, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: ctx.get("dtype") is DamageType.POISON,
    )


@power("f1812", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1812(c: Cast) -> None:
    amount = 5 + 5 * (c.level >= 11) + 5 * (c.level >= 21)
    c.resist(amount, DamageType.POISON, on=c.me, until=When.ENCOUNTER)


@power("f1801", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a fear power",
       on=Trigger(Miss, _missed_with(Keyword.FEAR), "you miss with fear"))
def f1801(c: Cast) -> None:
    c.slide(1, on=c.trigger.target)


@power("f1805", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an adjacent creature with an illusion power",
       on=Trigger(Hit, _my_illusion_encounter, "you hit with an illusion"))
def f1805(c: Cast) -> None:
    """The adjacency is asked after the blow rather than in the
    predicate, because a predicate gets no `Cast` and adjacency is a
    board question."""
    if c.adjacent(to=c.trigger.target):
        c.shift(1)


@power("f1806", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a melee illusion power",
       on=Trigger(Hit, _my_illusion_melee, "you hit with a melee illusion"))
def f1806(c: Cast) -> None:
    """Hiding from that one creature. `c.invisible(to=)` is the engine's
    form of "it cannot see you" and takes the single watcher, which is
    what this printed line is -- the Stealth check and the cover it
    depends on are both out of a fight's reach, so the hide is granted
    against that target and no other."""
    c.invisible(to=c.trigger.target, on=c.me, until=When.SONT)


@power("f1811", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.ignore_resistance()",))
def f1811(c: Cast) -> None:
    """Ignores poison resistance and immunity. Five item blocks already
    want the same verb: `Defences.resist` is read inside `deal_damage`
    and nothing lets an attacker step around it."""


@power("f1809", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus(dtype=)",))
def f1809(c: Cast) -> None:
    """One poisoned blow per rest.

    "The next attack with that weapon" is a `once=True` damage bonus, and
    the weapon is picked at the rest -- which is the moment this trait
    arms, since a fight begins after one. The dice ladder is the usual
    tier step.

    The *type* is dropped. `c.bonus` carries `dice` but no `dtype`, so
    the extra rolls untyped -- which is wrong against anything that
    resists poison, and is a whole sentence of the card rather than a
    rounding. `c.flat` takes a type and is not usable here: it pays
    immediately rather than riding on the next blow.
    """
    dice = "1d8" if c.level < 11 else "2d8" if c.level < 21 else "3d8"
    c.bonus("damage", 0, dice=dice, on=c.me, until=When.ENCOUNTER, once=True)


# -- the racial powers that arrive as refs ----------------------------------


@power("f1794", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p8278",
       on=Trigger(PowerUsed, _used("p8278"), "you use that racial power"))
def f1794(c: Cast) -> None:
    """Another shroud on whoever already carries one, when a named racial
    power goes off."""
    from combat_engine.engine.query import enemies

    for foe in enemies(c.world, c.me):
        if c.shrouds(foe):
            c.shroud(on=foe)
            return


@power("f2227", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget_defence()",))
def f2227(c: Cast) -> None:
    """Weapon attacks hit Reflex instead of AC while a named power holds
    you insubstantial. The power is `p2482` and `c.insubstantial` is
    readable -- what is missing is swapping the defence a row rolls
    against, which four item blocks also want."""


@power("f2819", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f2819(c: Cast) -> None:
    """Turns a named racial power from a close burst into an area burst
    at range. `p2473` is nameable; the reach is header data the menu
    reads before anything runs, and nothing rewrites one."""


@power("f2822", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2822(c: Cast) -> None:
    """Phasing while charging and while shade form holds.

    Both halves are askable: `Powers.times` says whether `p9402` is
    running, and the charge is a key the attack context carries. `c.phasing`
    takes no `when=`, so the gate is asked when the charge begins rather
    than per square -- which is the same answer, since neither the form
    nor the charge changes inside one move.
    """
    if _holding_form(c, SHADE):
        c.phasing(on=c.me, until=When.EOT)


@power("f2821", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7441",
       on=Trigger(PowerUsed, _used("p7441"), "you use that racial power"))
def f2821(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)


@power("f2815", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.expend_row()", "c.darkvision()"))
def f2815(c: Cast) -> None:
    """Spends shade form to get a named racial power back.

    Both are refs and `c.restore_use` takes one, so the giving half is
    ready -- what is missing is the paying half. `c.expended` *reads*
    which rows are spent and nothing spends one on purpose, which is the
    symbol an item block already names. Writing the restore without the
    cost would be the row's benefit with its price removed.

    Darkvision is the smaller clause and would not make the row playable
    on its own: sight in the dark is not modelled.
    """


@power("f2229", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a shrouded target with p1831",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1831"
       ), "you hit with that racial power"))
def f1831_rider(c: Cast) -> None:
    """Another shroud when a named racial power lands on a shrouded
    enemy."""
    foe = c.trigger.target
    if c.shrouds(foe) >= 1:
        c.shroud(on=foe)


@power("f1792", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1448",
       on=Trigger(Hit, _hit_with("p1448"), "you hit with that racial power"))
def f1792(c: Cast) -> None:
    """Invisibility to whatever a named racial power hit.

    `c.invisible(to=)` is the single-watcher form, which is what "to a
    creature hit by" is -- the rest of the board still sees you. The
    duration is the end of *your* turn, not your next one, so `When.EOT`
    rather than the method's `SONT` default.
    """
    c.invisible(to=c.trigger.target, on=c.me, until=When.EOT)


@power("f2228", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.lend_skills()",),
       trigger="you use p7546 and succeed on the check",
       on=Trigger(PowerUsed, _used("p7546"), "you use that power"))
def f2228(c: Cast) -> None:
    """No reprisals from whatever a named racial power fooled.

    The check is rolled inside `p7546`'s own body and `PowerUsed` fires
    before that body, so success is waited for rather than read -- the
    same shape `assassin_c`'s f2824 uses against this power, and
    `SkillCheck` carries `success` finished.

    The substitution is dropped: the card lets a Stealth check stand in
    for the Bluff one, and nothing puts one skill in another's place
    inside a row it does not own. So the no-reprisal half keys off the
    Bluff check `p7546` actually rolls, which is the printed effect
    whenever the assassin does not take the option.
    """
    me, foes = c.me, list(c.trigger.targets)
    done: list[bool] = []

    def on_check(ev: SkillCheck) -> None:
        if ev.actor != me or done or ev.skill != "bluff" or not ev.success:
            return
        done.append(True)
        for foe in foes:
            c.no_provoke(from_=foe, on=me, until=When.EONT)

    c.watch(SkillCheck, on_check, until=When.EOT, on=me)


@power("f2226", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you charge with p2480 against a shrouded enemy",
       on=Trigger(PowerUsed, _used("p2480"), "you use that racial power"))
def f2226(c: Cast) -> None:
    """An attack bonus and a shift on a named racial charge.

    The charge is the awkward half: neither `PowerUsed` nor
    `PowerResolved` carries one, so it cannot be asked in the predicate.
    It *is* a key of the attack context, so the bonus is laid here --
    `PowerUsed` fires before the body, in time for the roll -- and gated
    on `charge` per attack, which is exact. The shift is waited for on
    the `Hit`/`Miss`, where `charge` rides as a plain attribute and the
    shrouds can be counted on the creature actually struck.

    `once=True` on the bonus and a `done` latch on the watch each say
    "one firing"; the watch cannot use `once` for it, because an
    unrelated blow would spend it before the racial power landed.
    """
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.EOT, once=True,
        when=lambda ctx: (
            ctx.get("charge", False)
            and ctx.get("power") == "p2480"
            and ctx.get("target") is not None
            and c.shrouds(ctx["target"]) >= 1
        ),
    )

    done: list[bool] = []

    def after(ev: Any) -> None:
        if done or ev.attacker != me or ev.power != "p2480":
            return
        if not getattr(ev, "charge", False) or not c.shrouds(ev.target):
            return
        done.append(True)
        c.shift(max(1, c.speed_of() // 2))

    c.watch(Hit, after, until=When.EOT, on=me)
    c.watch(Miss, after, until=When.EOT, on=me)


# -- named by ref, and refused for some other reason ------------------------


@power("f1793", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.triggering_of()",))
def f1793(c: Cast) -> None:
    """Damage to whoever a named racial power's roll was aimed at.

    `m4421a6` is a ref, so this is no longer a naming gap. What is
    missing is the same thing `general_o`'s f3112 named against this very
    power: the racial power answers an attack roll, and a row answering
    the *use* has no way back to the roll being answered. `PowerUsed`
    carries the actor, the ref and the racial power's own targets, which
    are not "the target of that attack roll".
    """


@power("f1799", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f1799(c: Cast) -> None:
    """A free use of `p377` after a hit with a shadow power. Both halves
    are readable -- `Keyword.SHADOW` is on the row that was used and the
    racial power is a ref -- and what is missing is a row using another
    row, which sixteen rows already want."""


@power("f1803", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f1803(c: Cast) -> None:
    """A second power used free when `p1452` resolves. Same gap as f1799;
    `PowerResolved` is the event the "when the attack is resolved" half
    would be declared on, so the wait is not the obstacle."""


@power("f1807", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f1807(c: Cast) -> None:
    """Five squares further on `p1449`, if it ends beside a shrouded
    enemy. The power is a ref and `c.shrouds` answers the condition;
    nothing adds to the distance a *particular* row moves, which is the
    symbol `avenger_b`'s f1527 and the ranger's f786 both named."""


@power("f2812", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.as_implement(holy symbol)",))
def f2812(c: Cast) -> None:
    """Extra damage per shroud from a named power's damage.

    `p805` is a ref and `c.shrouds` counts, so the damage half is
    written. The holy-symbol half is dropped: `c.as_implement` rewrites
    the group of what is in hand, and a multiclass assassin's chassis
    carries no holy symbol to rewrite.
    """
    me = c.me
    c.bonus(
        "damage", 0, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p805",
    )
    for count in (1, 2, 3, 4):
        c.bonus(
            "damage", 1, on=me, until=When.ENCOUNTER, kind=f"{c.ref}:{count}",
            when=lambda ctx, n=count: (
                ctx.get("power") == "p805"
                and ctx.get("target") is not None
                and c.shrouds(ctx["target"]) >= n
            ),
        )


# -- waiting on the invoking, which nothing announces -----------------------


def _invoke(ref: str, what: str, *, wants: tuple[str, ...] = INVOKE) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} `c.shrouds` counts them and `c.shroud` lays one, but "
        "nothing announces the moment they are cashed in."
    )


_invoke("f1797", "Extra damage when you invoke and hit at once.")
_invoke("f1795", "A named racial power's damage invokes the shrouds too.")
_invoke("f1804", "A racial power pays extra when a miss still invokes.",
        wants=("c.on_invoke_shrouds()", "c.expend_row()"))
_invoke("f2233", "Leaving a named zone invokes the shrouds and clears them.",
        wants=("c.on_invoke_shrouds()", "c.on_leave_zone()"))


# -- waiting on a racial power that has no ref ------------------------------


def _racial(ref: str, what: str, *, wants: tuple[str, ...] = RACIAL) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The racial power is named in prose with no ref."


_racial("f1808", "A shroud when a racial trait's borrowed power is used.")
_racial("f2813", "Combat advantage from a target that has not yet acted.")
_racial("f2817", "A named racial power spent to get shade form back.")


# -- the rest ---------------------------------------------------------------


@power("f1802", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1802(c: Cast) -> None:
    """The printed narrowing is the *action*, which is what `SecondWind`
    carries `cost` for. Nothing in the tree yet grants a second wind for a
    minor, so this waits on a row that does."""
    if c.trigger.cost is not ActionType.MINOR:
        return
    c.restore_use("p9402")


@power("f2820", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f2820(c: Cast) -> None:
    """A cheaper cost for one row and only for this turn: the printed line
    is about this moment, not a standing discount."""
    c.recast("p9402", action=ActionType.FREE, until=When.EOT)


@power("f2814", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f2814(c: Cast) -> None:
    """Hands this character another class's feature outright. Sixteen
    rows already want the same verb; rods as implements is the smaller
    half and would not make the row playable on its own."""


@power("f2816", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f2816(c: Cast) -> None:
    """Extra damage per shroud from a class feature named in prose. The
    shroud half is ordinary; Flurry of Blows has no ref, which is the
    same gap four monk feats carry."""


@power("f2818", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use f2023b against your shroud target",
       on=Trigger(PowerUsed, _used("f2023b"), "you use that granted power"))
def f2818(c: Cast) -> None:
    """Upgrades what another *feat's* granted card does to a shrouded
    target. `f2023b` is a ref like any other, which is the whole point
    of minting a card for a feat that grants one."""
    for foe in c.trigger.targets:
        if not c.shrouds(foe):
            continue
        c.grants_advantage(on=foe, until=When.EONT)
        c.immobilized(on=foe, until=When.EONT)
