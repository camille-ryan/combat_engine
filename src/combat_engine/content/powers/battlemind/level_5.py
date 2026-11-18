"""Battlemind, level 5."""

from __future__ import annotations

from combat_engine.content.powers.augment import one_hit_rider
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    EACH_ENEMY,
    FREE,
    MOVE,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnStart,
    When,
    power,
    targets_me,
)

from . import shift_beside


@power(
    "p11165",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.POLYMORPH],
    attack=Attack(CON, vs=AC),
)
def p11165(c: Cast) -> None:
    """The aspect holds nothing of its own: resist 5 and the Wisdom rider are
    its Augment 1, and that clause is bought when some *other* row is
    augmented -- "while in this aspect you can use the following augmentation
    with your battlemind at-will attack powers that are augmentable", which
    `every=True` says.

    The resist is **all damage** and lasts to the end of the augmented row's
    turn, not the aspect's -- the clause runs during that use.
    """
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.prone()
    else:
        c.half_damage(c.w(), c.con_mod)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)

        wis = c.wis_mod

        def aspect(use: Cast) -> None:
            use.resist(5, until=When.EONT, on=use.me)
            one_hit_rider(use, wis, "p11165")

        c.lend_augment("battlemind", 1, aspect, every=True, on=c.me,
                       until=When.ENCOUNTER)


@power(
    "p11166",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=WILL),
)
def p11166(c: Cast) -> None:
    """**"The target's reach is reduced by 1" is written now.** The old note
    was right that `c.threatens` is the wrong verb -- it sets how far a
    creature threatens, not how far it can swing -- and wrong that nothing
    else reaches it. `"reach"` is a modifier key, read by `dsl.py`'s
    `mods.total("reach", ctx)` and by `movement.py`'s, and four rows were
    already laying one. One of them is `c.penalty("reach", ...)` in this
    very class's level 1. #1341.

    **"(minimum 1)" needs nothing here**: `movement.py` computes
    `max(1, 1 + mods.total("reach", ctx))`, so the floor is the engine's
    and a second guard in the row would be a copy of it.

    The slide is the other half of the same save-ends hold, so one save
    clears both.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)

    c.penalty("reach", 1, on=victim, until=When.SAVE_ENDS)

    def nudge(ev: Hit) -> None:
        if ev.target == victim and c.may("slide it", who=c.me):
            c.slide(1, on=victim)

    c.watch(Hit, nudge, until=When.SAVE_ENDS, on=victim)


@power(
    "p12423",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p12423(c: Cast) -> None:
    """The stance's move-action power is `p12423c0`, declared below and
    granted while the stance stands.

    **It could not be a second `@power` on this id and it does not have to
    be.** `dsl.entry_of` keeps a `c<n>` suffix as its own entry, which is
    the convention `Summon.commands` established, and `c.grant_row` has
    existed the whole time -- the old note said "not a thing `Cast` can
    grant", and what was missing was a row to grant rather than a verb.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.EONT)
    if c.last:
        if victim is not None:
            shift_beside(c, max(1, c.speed_of() // 2), victim)
        held = c.stance()
        if held is not None:
            c.grant_row("p12423c0", on=c.me, until=When.STANCE)


@power(
    "p13043",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.POLYMORPH],
    attack=Attack(CON, vs=WILL),
)
def p13043(c: Cast) -> None:
    """The aspect's Intimidate bonus is not a combat effect. Its Augment 1
    is a clause lent to *another* row's augment -- an at-will augmented
    while the aspect stands -- which `every=True` says.

    **"Each target of the at-will attack", not each target hit**, so this
    one needs no watcher: the target list is settled before any body runs
    and `Cast.targets` holds it, where the sibling aspects' "a creature hit
    by the attack" is only answerable once the use is over.
    """
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.damage("1d12", dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(), c.con_mod)
        c.half_damage("1d12", dtype=DamageType.PSYCHIC)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)

        def aspect(use: Cast) -> None:
            for who in use.targets:
                use.penalty("attack", 2, until=When.EONT, on=who)

        c.lend_augment("battlemind", 1, aspect, every=True, on=c.me,
                       until=When.ENCOUNTER)


@power(
    "p13044",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
    trigger="you take damage from an attack",
    on=Trigger(DamageApplied, targets_me, "you take damage from an attack"),
)
def p13044(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
        c.push(3)
    else:
        c.half_damage(c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
        c.push(1)
    if c.first:
        c.temp_hp(c.level // 2 + c.con_mod, on=c.me)


@power(
    "p13045",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13045(c: Cast) -> None:
    """The header's attack line is the *secondary* one; the primary target is
    only swapped with. `c.swap` is the named method for changing places, so
    the teleport keyword rides on a walk rather than a blink."""
    primary = c.target
    if primary is None:
        return
    c.swap(primary)
    reachable = c.within(1, side="enemy")
    victim = c.choose(reachable, "who you swing at") if reachable else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.damage(c.w(3), c.con_mod, on=victim)
    else:
        c.half_damage(c.w(3), c.con_mod, on=victim)
    c.mark(on=victim, until=When.EONT)


@power(
    "p13046",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p13046(c: Cast) -> None:
    """Both halves of the Effect play.

    **The teleport is a granted ordinary action, not a granted row, and the
    marker read it as the second.** It said *"a power in its own right
    sharing this id, so `c.grant_row` needs a ref to grant"*; the card
    prints *"you can teleport 2 squares as a free action"*, which is a line
    in the action menu that is normally absent -- exactly what
    `c.grant_action` is for. `"teleport"` is one of `actions.GRANTABLE`'s
    sixteen words and `squares_` is how far.

    `When.STANCE` is that verb's default and is the printed duration here,
    "until the stance ends", so the grant and the stance end together
    without being told to.
    """
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        c.stance()
        c.grant_action("teleport", FREE, squares_=2, on=c.me)


@power(
    "p2629",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p2629(c: Cast) -> None:
    """The stance's opportunity attack is `p2629b`, declared on its own now
    that the second printed block has an id, and gated on this stance
    standing rather than folded in here."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.last:
        c.stance()


@power(
    "p2631",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=AC),
)
def p2631(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.slide(1)
    else:
        c.half_damage(c.w(), c.con_mod)
    if not c.first:
        return

    def tug(ev: TurnStart) -> None:
        near = ev.actor in c.enemies() and c.distance(ev.actor) <= 3
        if near and c.may("slide it", who=c.me):
            c.slide(1, on=ev.actor)

    c.watch(TurnStart, tug, until=When.ENCOUNTER, on=c.me)


@power(
    "p12423c0",
    level=5,
    cls="",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p12423c0(c: Cast) -> None:
    """"Until the stance ends, you can move a number of squares equal to
    your speed + 1d4 as a move action. You roll a d4 each time you begin
    the movement. If the result is odd, the movement doesn't provoke
    opportunity attacks."

    `p12423`'s stance half, declared as its own row because that is what
    an extra action on the turn is -- `cls=""` so it joins no draw, and
    granted by `c.grant_row` for as long as the stance stands.

    **The d4 is rolled per movement and not once for the stance**, which
    the card says twice over, so it is rolled here in the body rather than
    recorded when the stance is assumed.

    The immunity is laid and ended around the step, so it is exactly as
    long as the move. `c.no_provoke` with a duration would have made every
    later step of the turn free as well.
    """
    rolled = c.roll("1d4")
    free = c.no_provoke(on=c.me) if rolled % 2 else None
    c.move(c.speed_of() + rolled, who=c.me)
    if free is not None:
        c.end_effect(free)
