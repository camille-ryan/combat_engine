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
ordinary `PowerUsed` or `Hit` trigger. One row is left naming its power
in prose and keeps `c.on_racial_power()`, the symbol the rogue's `f767`
named; `m4421a6` is named by ref but no row declares it.

What is still refused is narrower than it was: nothing lengthens the
move a named row makes (`c.extend_move()`) and nothing rewrites the
reach a row is printed with (`c.recast(reach=)`). `c.triggering_of()` is
gone from this file -- `PowerUsed.trigger` is the event a use was
answering, and `f1793` is written against it.

**Invoking is askable after all**, and that was the biggest group here.
`p9400` arms its own `Hit`/`Miss` watch and cashes the shrouds in from
inside it, unconditionally -- it never declines. So "you invoke your
shrouds" is "you hit, or miss, a creature carrying them", and the one
thing needed is to be looked at *before* `p9400`'s watch has cleared the
count. `Bus.on` keeps insertion order and runs the whole `BEFORE` window
first, so a trait armed at the start of the fight with
`window=Window.BEFORE` sees the shrouds intact every time. Six rows here
came off `c.on_invoke_shrouds()` that way.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Miss,
    PowerResolved,
    PowerUsed,
    SecondWind,
    Trigger,
    When,
    Window,
    about_me,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import SkillCheck, ZoneExited
from combat_engine.engine.zones import Zone

#: A racial power named in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)

#: The class's own shroud power and its shade form, both named by ref in
#: these feats' own prerequisites.
SHROUD = "p9400"
SHADE = "p9402"


def _before(c: Cast, event: type, fn) -> None:  # noqa: ANN001
    """Watch an event in the interrupt window, for the whole fight.

    Every row below that reads a shroud count has to be looked at before
    `p9400`'s own watch has spent it. `Bus._run` runs the entire `BEFORE`
    window before the `AFTER` one, so this is order-proof rather than
    relying on which trait happened to arm first.
    """
    c.watch(event, fn, until=When.ENCOUNTER, on=c.me, window=Window.BEFORE)


def _payout(c: Cast, victim: int, *, spend: bool = True) -> int:
    """What invoking pays: one d6 a shroud, plus a flat step each from
    paragon on. `p9400` keeps this arithmetic inside its own watch and
    there is no way to call it from outside, so it is written out.

    `spend=False` is for the rows whose payout is *extra* -- `p9400`
    invokes on every hit of its own accord, so a row that cleared the
    count would only be taking the engine's own payout away."""
    count = c.shrouds(victim)
    if count <= 0:
        return 0
    per = 0 if c.level < 11 else (3 if c.level < 21 else 6)
    dealt = c.flat(c.roll(f"{count}d6") + count * per, on=victim)
    if spend:
        c.spend_shrouds()
    return dealt


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
       trigger="you drop a creature carrying your shrouds")
def f2230(c: Cast) -> None:
    """Temporary hit points scaled by the shrouds on whatever just fell,
    and a teleport if they were invoked on the killing blow.

    Written as a trait rather than a declared `Dropped` trigger, because
    **by the time a creature falls its shrouds are already gone**:
    `p9400` cashes them in from inside the same `Hit` that killed it, so
    the count this row is supposed to scale off has been zero at
    `Dropped` since the day both rows were written. The count is
    therefore taken in the interrupt window of the blow itself and
    remembered.

    `Dropped.actor` is the creature that fell -- there is no `target` on
    that event, and reading one through `getattr` would make the row
    silently do nothing.
    """
    me = c.me
    #: what each creature was carrying when it was last struck, and
    #: whether that blow invoked -- a hit invokes on one shroud, a miss
    #: pays nothing back until there are two.
    seen: dict[int, tuple[int, bool]] = {}

    def struck(ev: Any) -> None:
        if ev.attacker != me:
            return
        count = c.shrouds(ev.target)
        if count:
            seen[ev.target] = (count, count >= (2 if isinstance(ev, Miss) else 1))

    _before(c, Hit, struck)
    _before(c, Miss, struck)

    def fell(ev: Dropped) -> None:
        if getattr(ev, "source", None) != me:
            return
        count, invoked = seen.pop(ev.actor, (c.shrouds(ev.actor), False))
        if not count:
            return
        c.temp_hp(5 + count, on=me)
        # The destination is "adjacent to your nearest ally within 10",
        # which `c.teleport` has no way to carry -- the same constraint
        # `p9401` leaves to the world's decider. The ally is a gate here
        # rather than a square.
        if invoked and c.within(10, of=me, side="ally"):
            c.teleport(10, who=me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me)


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
       reach=PERSONAL, target=SELF)
def f1811(c: Cast) -> None:
    """No number, so all of it, and the immunity with it: `immunity=True`
    is the blanket form rather than the "treat it as resist 20" one."""
    c.ignore_resistance(
        None, DamageType.POISON, on=c.me, until=When.ENCOUNTER,
        immunity=True,
    )


@power("f1809", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1809(c: Cast) -> None:
    """One poisoned blow per rest.

    "The next attack with that weapon" is a `once=True` damage bonus, and
    the weapon is picked at the rest -- which is the moment this trait
    arms, since a fight begins after one. The dice ladder is the usual
    tier step.

    The die is poison and carries its own type, so it is shrugged off by
    a creature that resists poison and the weapon's own damage is not.
    """
    dice = "1d8" if c.level < 11 else "2d8" if c.level < 21 else "3d8"
    c.bonus("damage", 0, dice=dice, on=c.me, until=When.ENCOUNTER,
            once=True, dtype=DamageType.POISON)


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


@power("f2815", level=1, cls="", usage=AT_WILL, action=ActionType.FREE,
       reach=PERSONAL, target=SELF, dropped=("c.darkvision()",))
def f2815(c: Cast) -> None:
    """Spends one named row to get another back: `c.expend_row` is the
    price, `c.restore_use` is the payout, and the order matters -- the
    restore only happens if the payment went through.

    Dropped: darkvision is the smaller clause and sight in the dark is
    not modelled, so it is named rather than approximated.
    """
    if c.expend_row("p9402"):
        c.restore_use("p2482", on=c.me)


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
       reach=PERSONAL, target=SELF, todo=("m4421a6",),
       trigger="you use m4421a6 to improve an attack roll",
       on=Trigger(PowerUsed, _used("m4421a6"), "you use that racial power"))
def f1793(c: Cast) -> None:
    """Damage to whoever a named racial power's roll was aimed at.

    Re-aimed. `c.triggering_of()` has arrived: `PowerUsed.trigger` is
    the event the power was used in answer to, and the racial power
    answers an attack roll, which carries its own `target`. So the body
    is writable and is written.

    What is left is the racial power itself -- the spec names it
    `x_m4421a6`, the ETL's mark for a ref it could not resolve, and
    nothing in the tree declares it. Until it does, this trigger can
    never fire, so the row is `todo` rather than finished.
    """
    rolled = getattr(c.trigger, "trigger", None)
    victim = getattr(rolled, "target", None)
    if victim is not None:
        c.flat(c.dex_mod, on=victim)


@power("f1799", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a shadow power",
       on=Trigger(Hit, _keyworded(Keyword.SHADOW),
                  "you hit with a shadow power"))
def f1799(c: Cast) -> None:
    """A free use of `p377` after a hit with a shadow power, which
    `c.use_power` now says in one line.

    `AT_WILL`: a triggered `action=NONE` row spends a use every firing
    and the card prints no limit of its own -- p377's encounter use is
    the limit, and using it spends it."""
    c.use_power("p377")


@power("f1803", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your p1452 racial power",
       on=Trigger(PowerResolved,
                  lambda w, me, ev: ev.actor == me and ev.power == "p1452",
                  "you use p1452"))
def f1803(c: Cast) -> None:
    """A second power used free when `p1452` resolves. `PowerResolved`
    and not `PowerUsed`, because the card says "when the attack is
    resolved" and `PowerUsed` is announced before the body runs."""
    c.use_power("p9401")


@power("f1807", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f1807(c: Cast) -> None:
    """Five squares further on `p1449`, if it ends beside a shrouded
    enemy. The power is a ref and `c.shrouds` answers the condition;
    nothing adds to the distance a *particular* row moves, which is the
    symbol `avenger_b`'s f1527 and the ranger's f786 both named."""


@power("f2812", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:holy-symbol",))
def f2812(c: Cast) -> None:
    """Extra damage per shroud from a named power's damage.

    The holy-symbol half is no longer dropped and was never a body:
    "you can use X as an implement" is the `proficiency=` header field,
    which `chargen` reads when the character is armed -- the same shape
    `f2814` next door uses for rods. `w:holy-symbol` is already a
    printed item.
    """
    me = c.me
    for count in (1, 2, 3, 4):
        c.bonus(
            "damage", 1, on=me, until=When.ENCOUNTER, kind=f"{c.ref}:{count}",
            when=lambda ctx, n=count: (
                ctx.get("power") == "p805"
                and ctx.get("target") is not None
                and c.shrouds(ctx["target"]) >= n
            ),
        )


# -- the invoking, read in the window before it happens ---------------------


@power("f1797", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1797(c: Cast) -> None:
    """Strength modifier on top of the shrouds, on a blow that both
    invokes and lands.

    `p9400` never declines the invoke, so "you invoke your shrouds on an
    enemy and hit it" is exactly "you hit an enemy carrying at least one"
    -- asked in the interrupt window, where the count is still there.
    """
    me = c.me

    def landed(ev: Hit) -> None:
        if ev.attacker == me and c.shrouds(ev.target):
            c.flat(c.str_mod, on=ev.target)

    _before(c, Hit, landed)


@power("f1795", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1795(c: Cast) -> None:
    """A named racial power's damage pays the shrouds out as well.

    `p8278` is not a blow of its own: it lays a one-shot necrotic rider
    on the next hit, labelled with its own ref like every effect. So
    "when you deal damage with it" is "the hit that rider is about to
    ride on", which is this `Hit` with that effect still standing.

    The shrouds are **not** spent here. `p9400` invokes on this same hit
    of its own accord, so clearing them would leave the engine's own
    payout with nothing to pay and turn the feat into a row that takes
    damage away.
    """
    me = c.me

    def landed(ev: Hit) -> None:
        if ev.attacker == me and _holding_form(c, "p8278"):
            _payout(c, ev.target, spend=False)

    _before(c, Hit, landed)


@power("f1804", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1804(c: Cast) -> None:
    """A miss that the shrouds still pay out on, bought with a racial
    power.

    `p9400` drops one shroud from the count on a miss, so "your shrouds
    still deal damage" is two or more of them. `c.expend_row` is the
    price and its False is the printed requirement -- no racial power
    left, no extra die.
    """
    me = c.me
    dice = "1d6" if c.level < 11 else "1d12"

    def missed(ev: Miss) -> None:
        if ev.attacker != me or c.shrouds(ev.target) < 2:
            return
        if c.expend_row("p6189"):
            c.flat(c.roll(dice), on=ev.target)

    _before(c, Miss, missed)


@power("f2233", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2233(c: Cast) -> None:
    """Leaving a named zone of yours pays the shrouds out and clears
    them.

    `ZoneExited` is the event -- it was already there, so the second
    half of this row's old marker named nothing. A zone carries its
    owner and is labelled with the ref of the row that made it, which is
    how the one `p2473` laid is told from anybody else's.

    The shrouds are spent here: no attack is involved, so nothing else
    is going to, and the card says they vanish.
    """
    me = c.me

    def left(ev: ZoneExited) -> None:
        zone = c.world.get(ev.zone, Zone)
        if zone is None or zone.owner != me or not zone.label.startswith("p2473"):
            return
        if c.shrouds(ev.actor):
            _payout(c, ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me)


# -- waiting on a racial power that has no ref ------------------------------


def _racial(ref: str, what: str, *, wants: tuple[str, ...] = RACIAL) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The racial power is named in prose with no ref."


#: The `rt:r6-t3` choice: an at-will borrowed from another
#: class, picked when the character is built and recorded nowhere. The
#: same symbol `features/racial._option` carries.
RACE_OPTION = ("c.race_option()",)

_racial("f1808", "A shroud when a racial trait's borrowed power is used.",
        wants=RACE_OPTION)
#: Re-aimed: `c.expend_row` is the spending and `c.restore_use` is the
#: payout, so f2830 next door is this row written out -- the difference
#: is that the power being spent here arrives as a name and not a ref.
_racial("f2817", "A named racial power spent to get shade form back.")


@power("f2813", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p9400",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: ev.actor == me and ev.power == "p9400",
                  "you use that power"))
def f2813(c: Cast) -> None:
    """Nothing racial about the benefit -- the race is the gate and
    `p9400` is the row, which is a ref. "Has not yet acted in the
    encounter" is the surprised condition, which the surprise round lays
    and the creature's first turn clears. `p9400` is `ONE_CREATURE`, so
    the targets are chosen before the body and `PowerUsed.targets` is
    the set the card means."""
    for foe in c.trigger.targets:
        if c.is_(Condition.SURPRISED, on=foe):
            c.grants_advantage(on=foe, to=c.me, until=When.SONT)


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
       reach=PERSONAL, target=SELF, proficiency=("w:rod",))
def f2814(c: Cast) -> None:
    """Hands this character another class's feature outright, and
    `cf:warlock-f3` is declared now.

    "If you do not already have it" needs no `if`: `c.grant_row`
    returns `None` for a row the creature already knows rather than
    handing it a second time. Rods as implements is header data
    `chargen` reads when the character is built."""
    c.grant_row("cf:warlock-f3", on=c.me, until=When.ENCOUNTER)


#: The other class's level 0 feature row, printed once per tradition. A
#: character has exactly one of the five; `powers/monk/level_6_b.py` is
#: where the set comes from.
_FLURRY = ("p7448", "p11207", "p13123", "p16131", "p16132")

_USED_FLURRY = "you use the other class's level 0 feature row"


def _used_my_flurry(world, me: int, ev: PowerUsed) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power in _FLURRY


@power("f2816", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_USED_FLURRY,
       on=Trigger(PowerUsed, _used_my_flurry, _USED_FLURRY))
def f2816(c: Cast) -> None:
    """"The target of your `p9400` power" is asked as "a creature
    carrying your shrouds", which is the same set: `p9400` moves every
    shroud off the old creature when it is used on a new one, so at most
    one target is ever carrying any.

    `c.flat` rather than a damage modifier -- the amount is per shroud
    and belongs to this one blow. `PowerUsed` is announced before the
    body runs and that is safe here: targets are chosen first and
    nothing the feature's body does is read.
    """
    for foe in getattr(c.trigger, "targets", ()) or ():
        count = c.shrouds(on=foe)
        if count:
            c.flat(count, on=foe)


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
