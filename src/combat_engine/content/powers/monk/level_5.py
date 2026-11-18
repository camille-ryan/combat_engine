"""Monk, level 5: the dailies.

These print one stat block rather than two, so there is no move half unless
the Effect line says so -- and where it does (p16159) the movement comes
first and the attack is made from where it ends.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    DEX,
    EACH_OTHER,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageType,
    ForcedMove,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    Window,
    both,
    by_melee,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import (
    Hit,
    Moved,
    PowerResolved,
    TurnEnd,
)

from .level_0 import FLURRIES

# Psionic is printed on every one of these cards and the constant
# omitted it, so 28 rows declared half their keyword line -- the
# `MARTIAL_WEAPON` idiom the fighter files use, missing its source.
# #486.
PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]


def _melee(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in ("melee", "close_burst", "close_blast")


@power(
    "p11220",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11220(c: Cast) -> None:
    """The retaliation is tied to the mark rather than given a duration of
    its own: the printed line ends when this power's mark does."""
    if c.strike():
        c.damage("3d10", c.dex_mod)
        held = c.mark(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d10", c.dex_mod)
        held = c.mark(until=When.EONT)
    victim = c.target
    if victim is None or held is None:
        return

    def sting(ev: Hit) -> None:
        if ev.attacker == victim and ev.target == c.me:
            c.flat(c.str_mod, on=victim, from_attack=False)

    watcher = c.watch(Hit, sting, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "mark ended"))


@power(
    "p11221",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p11221(c: Cast) -> None:
    """**The "lengthen the forced movement instead" option is written, and
    the shape the note asked for is what it needed: a hold that lengthens
    the shove when there is one and falls back to the slide when there is
    not.**

    The note had the difficulty exactly right. The card prints a *choice*
    -- *"increase the distance of that movement by 1 square **instead of**
    sliding the target 1 square"* -- and `Hit` fires before the shove, so
    a `c.forces` armed unconditionally alongside the slide pays out
    **both**, which is strictly stronger than print and would show up
    nowhere.

    What resolves it is that **the shove announces itself before it
    happens**: `ForcedMove` is a `Decision` emitted with `source`,
    `target`, `how` and `squares` while the distance is still being
    settled. So the order is:

    1. on `Hit`, arm a one-shot `ForcedMove` watch and remember nothing
       has shoved yet;
    2. if that attack shoves this target, lengthen it by one and mark the
       choice taken;
    3. at the **end** of the hit's resolution, slide 1 only if it was not.

    The third step needs a moment of its own, and `PowerResolved` is it:
    the slide has to wait until the attack's own forced movement would
    have happened, which is after every other clause of the Hit line.
    `f1827` takes the same route for the same reason -- *"declared on
    `PowerResolved`, not on `Hit`"* -- and it is the one event that is
    reliably after them all.

    `once=True` on the lengthening watch, so one attack lengthens one
    shove: the card says "that movement", not every shove in the
    encounter."""
    if c.strike():
        c.damage("3d10", c.dex_mod)
    else:
        c.half_damage("3d10", c.dex_mod)
    victim = c.target
    if victim is None:
        return
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx, v=victim: ctx.get("target") == v, kind="power")

    def herd(ev: Hit) -> None:
        if ev.attacker != c.me or ev.target != victim:
            return
        # **The choice, settled by whether this attack shoves.** A
        # `ForcedMove` is a `Decision` announced before the distance is
        # applied, so a one-shot watch can lengthen it -- and the slide
        # below only happens if nothing did.
        lengthened = [False]

        def shoved(move: ForcedMove) -> None:
            if lengthened[0] or move.source != c.me or move.target != victim:
                return
            lengthened[0] = True
            move.squares += 1

        watching = c.watch(ForcedMove, shoved, until=When.EOT,
                           window=Window.BEFORE)

        def settle(done: PowerResolved) -> None:
            if done.actor != c.me or done.power != ev.power:
                return
            if watching is not None and not watching.ended:
                c.world.effects.end(watching, "the hit is over")
            if not lengthened[0]:
                c.slide(1, on=victim)

        c.watch(PowerResolved, settle, until=When.EOT, once=True)

    c.watch(Hit, herd, until=When.ENCOUNTER)


@power(
    "p13154",
    level=5,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.STANCE],
)
def p13154(c: Cast) -> None:
    posture = c.stance()
    held = c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_melee, kind="power")
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p13156",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.COLD],
    attack=Attack(DEX, vs=REF),
)
def p13156(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.COLD)
        held = c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.dex_mod, dtype=DamageType.COLD)
        held = c.slowed(until=When.SAVE_ENDS)
    victim = c.target
    if victim is None or held is None:
        return

    def chill(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == c.me or ev.actor not in c.enemies():
            return
        if c.adjacent_to(victim, ev.actor):
            c.flat(c.dex_mod, dtype=DamageType.COLD, on=ev.actor, from_attack=False)

    watcher = c.watch(TurnEnd, chill, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "the hold ended"))


@power(
    "p13157",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13157(c: Cast) -> None:
    """Miss deals the same damage as a hit, so the roll is unconditional
    and only the vulnerability hangs off landing."""
    landed = bool(c.strike())
    c.damage("2d6", c.dex_mod)
    if not landed:
        return
    held = c.vulnerable(c.str_mod, until=When.SAVE_ENDS)
    victim = c.target
    if victim is None or held is None:
        return

    def nag(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.penalty("save", 2, on=victim, until=When.SAVE_ENDS, once=True)

    watcher = c.watch(Hit, nag, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "vulnerability ended"))


@power(
    "p13158",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=REF),
)
def p13158(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
        for near in c.within(1, of=c.target, side="any"):
            if near != c.target:
                c.prone(on=near)
    else:
        c.half_damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)


@power(
    "p15986",
    level=5,
    cls="monk",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
    trigger="an adjacent enemy hits you with a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an adjacent enemy hits you in melee"),
)
def p15986(c: Cast) -> None:
    """The charge rider is read off the triggering event, where the flag
    lives.

    **The Miss line is written now**, and "has no expression" was false:
    it is two verbs that both already existed. `c.restore_use` hands the
    daily back -- its own docstring is about rows whose entire effect is
    that line -- and `c.forbid` is the other half, "cannot use it again
    during this encounter", which is exactly the thing `c.forbid`
    distinguishes from spending a use: a forbidden row is one the
    creature still owns and cannot reach. #1341.

    **Both halves, or neither is the card.** Giving the use back alone
    makes the miss a free retry; forbidding alone just spends the daily
    twice over. The order is restore-then-forbid so the forbid has
    something to sit on.
    """
    charged = bool(getattr(c.trigger, "charge", False))
    if c.strike(plus=2 if charged else 0):
        c.damage("3d10", c.dex_mod)
        if charged:
            c.flat(c.roll("1d10"))
        c.slide(2)
        c.prone()
    else:
        c.restore_use(c.ref)
        # **`on=c.me`, and the default is the TARGET.** `c.forbid` takes
        # its creature from `_who`, like `c.flat` and `c.temp_hp`, so the
        # first draft forbade this row to the *enemy* that triggered it --
        # measured as the monk still able to use the power after a miss,
        # which is the free retry this clause exists to prevent.
        c.forbid(c.ref, on=c.me, until=When.ENCOUNTER)


@power(
    "p16156",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.STANCE],
    attack=Attack(DEX, vs=FORT),
)
def p16156(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.dex_mod)
    else:
        c.half_damage("2d6", c.dex_mod)
    if c.last:
        c.stance(conditions=[Condition.SLOWED])


@power(
    "p16158",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16158(c: Cast) -> None:
    """The aftereffect is hung on the daze's own ending, which is the only
    moment "after it saves" happens."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        held = c.dazed(until=When.SAVE_ENDS)
        victim = c.target
        if held is not None and victim is not None:
            held.on_end.append(lambda: c.slowed(on=victim, until=When.EOTNT))
    else:
        c.half_damage("2d8", c.dex_mod)
        c.slowed(until=When.EONT)


@power(
    "p16159",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.FIRE, Keyword.ZONE, Keyword.ELEMENTAL],
    attack=Attack(DEX, vs=REF),
)
def p16159(c: Cast) -> None:
    """The move is printed before the attack and the zone is the trail it
    leaves, so the squares are collected from the steps themselves."""
    if c.first:
        trail: list[object] = []

        def step(ev: Moved) -> None:
            if ev.actor == c.me:
                trail.append(ev.from_)

        sub = c.world.bus.on(Moved, step)
        try:
            c.move(c.speed_of())
        finally:
            c.world.bus.off(sub)
        if trail:
            burnt = c.zone(trail, until=When.EONT)
            c.burns(burnt, c.dex_mod, DamageType.FIRE)
    if c.strike():
        c.damage("4d6", 0, dtype=DamageType.FIRE)
    else:
        c.half_damage("4d6", 0, dtype=DamageType.FIRE)


@power(
    "p7461",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_IMPLEMENT, Keyword.POISON],
    attack=Attack(DEX, vs=FORT),
)
def p7461(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d10", c.dex_mod)


@power(
    "p7462",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7462(c: Cast) -> None:
    """**The marker said the feature had "no id in the spec", and the ids
    were there all along.** The Effect line widens the class feature, which
    the spec names in prose -- but the feature is five printed build
    options with five refs, written down as `FLURRIES` in `level_0.py` and
    mirrored as `cf:monk-f0c0`..`c4`. `p11215` already reads that list to
    tell which row the feature is on the creature in front of it. So this
    was never a spec gap, and the symbol pointed at `etl` for a clause the
    engine owed.

    **And it was not the facility gap the re-pointing would have named
    either.** `f3304` waits on `c.extra_target()` and `f3793`'s note argues
    that verb is not owed at all -- `c.add_target` appends to a use already
    running, and what it cannot do is reach one that has not started. That
    is the right diagnosis and the wrong conclusion for this card: the
    printed clause moves the **target line**, not a running use, and
    `dsl.target_of` has been the per-creature door for that since `#712`.

    So the Effect is one call per variant held. Driven end to end at a
    board with four adjacent enemies, the feature lands on **1** target
    plain and **2** after this row, which is the whole clause.

    One variant on a dealt monk; the audit board composes a hand by hand
    and deals all five, so the loop lays five effects there, each gated to
    its own ref. Harmless and deliberate -- an effect for a row the
    creature cannot use is never consulted.
    """
    if c.strike():
        c.damage("3d8", c.dex_mod)
        c.push(2)
    else:
        c.half_damage("3d8", c.dex_mod)
        c.push(1)
    # "Until the end of your next turn" -- the caster's, so EONT.
    for flurry in FLURRIES:
        if c.knows(flurry):
            c.extra_target(ref=flurry, until=When.EONT)
