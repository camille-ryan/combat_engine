"""Assassin, level 7."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Target,
    TurnEnd,
    TurnStart,
    When,
    power,
    spread,
)
from combat_engine.engine.query import squares


@power(
    "p16478",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p16478(c: Cast) -> None:
    """"Including those with blindsight or tremorsense" is a sense model the
    engine does not keep, and "or until you attack" is a break condition
    `c.invisible` does not take -- `c.hide` has it, but not the clock."""
    victim = c.target
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.PSYCHIC)
    for foe in c.enemies():
        if foe != victim:
            c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "p9431",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9431(c: Cast) -> None:
    """The deferred free action is resolved at once: nothing here can hand a
    creature an action to spend on a later turn."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        free = [s for s in spread({c.here}, 1) if not c.in_squares([s])]
        if free:
            c.teleport(5, who=victim, to=sorted(free)[0])


@power(
    "p9432",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW, Keyword.TELEPORTATION],
    attack=Attack(DEX, vs=WILL),
    dropped=("c.grant_action(toward=)",),
)
def p9432(c: Cast) -> None:
    """**The build rider's teleport is written and the marker was wrong
    about why.** It said the rider *"grants a minor-action teleport on a
    later turn, which is an action nothing can hand out"*, and
    `"teleport"` is one of `actions.GRANTABLE`'s sixteen words --
    `c.grant_action("teleport", MINOR, squares_=...)` hands out exactly
    that, which is the idiom `p11175` and `p13046` use for the same
    sentence.

    `c.build("f1s2")` is the gate, which is how every other rider in this
    class reads its build.

    **What is left is the proviso, and it is a narrower marker.** The card
    says *"you must end the teleportation closer to the target"*, and
    `c.grant_action` carries a distance and no destination test -- the
    grant it writes is the ordinary teleport, which may end anywhere in
    range. `c.teleport` itself takes `toward=` for precisely this shape,
    so the gap is passing that through the grant rather than anything
    larger; hence `c.grant_action(toward=)` and not a row-granting
    facility.

    "During your next turn" is `When.EONT`, which is the nearest duration
    the enum has -- the grant is spent on that turn or lapses with it.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.dex_mod, dtype=DamageType.PSYCHIC)

        def late(ev: TurnEnd) -> None:
            if ev.actor == victim and len(c.within(2, of=victim)) > 1:
                c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

        c.watch(TurnEnd, late, until=When.ENCOUNTER, once=True)

        if c.build("f1s2") and c.cha_mod > 0:
            c.grant_action("teleport", MINOR, squares_=c.cha_mod, on=c.me,
                           until=When.EONT)


@power(
    "p9433",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
    dropped=("c.miss_lands_on(on=)",),
)
def p9433(c: Cast) -> None:
    """Sharing the target's square is `share=True`; moving with it is riding
    it, which is the relation that makes a creature carry another.

    "Any melee or ranged attack that misses you hits the target instead" is
    still dropped, and the reason has been narrowed: the old note said it
    "needs a redirect from inside the attack's own interrupt window", and
    that window is reachable -- `c.pass_on`'s docstring demonstrates it,
    and `c.redirect` is a verb that lives in it.

    Three near misses, and what each cannot do:

    * `c.redirect` moves the blow **with its live result**, so a miss
      stays a miss wherever it is pointed.
    * `c.also_hits` copies a blow that has already landed, by watching the
      `DamageRolled` that attack makes -- a miss rolls none, so there is
      nothing to copy.
    * `c.hit_becomes(True)` forces the blow that was answered to land, on
      the creature it was already aimed at, not on a second one.

    What the card asks for is a **standing** hold that turns a miss on one
    creature into a hit on another, and none of the three is that."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.shift(1, to=c.there, share=True)
        c.insubstantial(on=c.me, until=When.SONT)
        c.ride(on=victim)

        def step_off(ev: TurnStart) -> None:
            if ev.actor != c.me:
                return
            free = [s for s in spread(squares(c.world, victim), 1) if not c.in_squares([s])]
            if free:
                c.slide(1, on=c.me, to=sorted(free)[0])

        c.watch(TurnStart, step_off, until=When.ENCOUNTER, once=True)


#: The printed Target line: the creature the assassin's shrouds are on.
#: Declared rather than gated in the body, which is how `ranger`'s
#: `_QUARRY` and `warlock`'s cursed targets spell the same shape --
#: a restriction the player aims by, not a refusal the row makes of itself.
_SHROUDED = Target("enemy", 1, label="The creature your shrouds are on")


@power(
    "p9434",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=_SHROUDED,
    keywords=[Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9434(c: Cast) -> None:
    """**Shrouds ARE modelled and the old note said they were not.**
    `c.shroud` lays one, `c.shrouds` counts them and `c.spend_shrouds`
    cashes them in. #1341.

    So the printed Target -- "your `p9400` target" -- is declared in the
    target line, which is where a restriction the player aims by belongs.

    The Hit rider is **not** written, and the corrected reason is
    narrower than "shrouds are not modelled": the clause is *"you can use
    your `p9400` against the target whenever you are hit"*, which grants
    extra **uses** of another row on somebody else's trigger. That is a
    usage-limit change, the same shape `p14399`'s free shroud waits on,
    and not a shroud question at all."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        if c.build("f1s0") and c.con_mod > 0:
            c.temp_hp(c.con_mod, on=c.me)
