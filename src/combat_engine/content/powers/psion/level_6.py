"""Psion, level 6: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import spent_on
from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AttackDeclared,
    Cast,
    DamageRolled,
    Dropped,
    Effect,
    Healed,
    Hit,
    Keyword,
    Miss,
    Ranged,
    SavingThrow,
    Trigger,
    When,
    Window,
    World,
    ally_within,
    both,
    by_keyword,
    by_me,
    get,
    power,
    query,
)
from combat_engine.engine.events import Moved

PSIONIC = [Keyword.PSIONIC]


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and ev.critical


def _unaugmented_at_will(world: World, me: int, ev: Any) -> bool:
    """"With an unaugmented at-will power", as a predicate.

    `augment.spent_on` is what the use being answered paid; the pool's own
    `augmented` total says the row was augmented *at some point this
    encounter*, which is a different sentence and true far too often."""
    p = get(getattr(ev, "power", ""))
    return p is not None and p.usage is AT_WILL and not spent_on(me, ev.power)


def _my_will(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and ev.vs == WILL


def _made_it(world: World, me: int, ev: Any) -> bool:
    return bool(ev.saved)


@power(
    "p11318",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an enemy scores a critical hit against you",
    on=Trigger(Hit, _crit_on_me, "an enemy scores a critical hit against you"),
)
def p11318(c: Cast) -> None:
    """Reducing *one* attack's damage is a one-shot listener on the damage
    roll, in the window before it lands -- `c.resist` would shave everything
    else that reached you in the same turn as well."""
    cut = 10 + c.wis_mod
    spent = [False]

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me and not spent[0]:
            spent[0] = True
            ev.amount = max(0, ev.amount - cut)

    c.watch(
        DamageRolled,
        soften,
        until=When.EOT,
        window=Window.BEFORE,
        on=c.me,
        label=c.ref,
    )


@power(
    "p13327",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you hit an enemy within 10 squares with a psionic force at-will",
    on=Trigger(
        Hit,
        both(
            by_me,
            by_keyword(Keyword.FORCE),
            by_keyword(Keyword.PSIONIC),
            _unaugmented_at_will,
        ),
        "you hit an enemy with an unaugmented psionic force at-will",
    ),
)
def p13327(c: Cast) -> None:
    """The whole printed trigger is declared now that an augment is a real
    spend: "unaugmented" and "at-will" are both askable of the row the `Hit`
    names. The gate is in the predicate rather than the body because an
    encounter power is marked used before its body runs, so a body that
    bowed out would cost the use anyway."""
    ev = c.trigger
    if ev is None:
        return
    for near in c.within(1, of=ev.target, side="any"):
        if near not in (ev.target, c.me):
            c.grants_advantage(on=near, until=When.EONT, to="team")


@power(
    "p13328",
    level=6,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.CONJURATION],
    narrative=("skill:perception",),
)
def p13328(c: Cast) -> None:
    """The prism goes on the board and can be pushed about at Intelligence
    modifier squares a turn.

    **The three dropped clauses are written, and the "+4 bonus to all
    defenses" needed the page to read correctly.** PHB2 p221's Appendix
    entry for CONJURATION is the governing rule and `c.conjure`'s docstring
    quotes it: *"If a conjuration can be attacked or physically affected,
    it uses your defenses."* So the caster's four are the **baseline** and
    the card's +4 is on top of them -- `defences_plus=4`. Read as an
    absolute it would have given the prism defences of 4, which is lower
    than anything on the board and the opposite of what the card does.

    *"Hit points equal to your healing surge value"* is `hp=c.surge_value()`.

    *"If the prism drops to 0 hit points, it is destroyed and you are dazed
    until the end of your next turn"* is a `Dropped` watch on the prism's
    own entity. `_check_down` emits that for anything with `Health` that
    reaches zero, creature or not, so the conjuration announces its own
    destruction and nothing had to be added for it.

    *"You can use your attack powers as if you were in the prism's space"*
    is `c.cast_from(optional=True)`: the card says *can*, so it is the
    choice form rather than the replacement -- a psion forced to cast from
    the prism would be worse off than the card leaves them.

    The Perception bonus is the one clause with no combat meaning, so it is
    `narrative=` rather than dropped: +3 while the prism is adjacent, and
    nothing in a fight reads it.
    """
    prism = c.conjure(until=When.ENCOUNTER, sustain=None, speed=c.int_mod,
                      defences_of=c.me, defences_plus=4, hp=c.surge_value())
    if not prism:
        return
    c.cast_from(prism, optional=True, until=When.ENCOUNTER)

    def shattered(ev: Dropped) -> None:
        if ev.actor == prism:
            c.dazed(on=c.me, until=When.EONT)

    c.watch(Dropped, shattered, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p13329",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an enemy attack targets your Will",
    on=Trigger(AttackDeclared, _my_will, "an enemy attack targets your Will"),
)
def p13329(c: Cast) -> None:
    """Declared on the attack rather than on the hit: the bonus has to be up
    before the roll is compared, and whether it missed is only known
    afterwards, so the second half of the line is a listener on `Miss`."""
    ev = c.trigger
    c.bonus(WILL, 4, on=c.me, until=When.EONT)
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return

    def missed(m: Miss) -> None:
        if m.attacker == foe and m.target == c.me:
            c.grants_advantage(on=foe, until=When.EONT, to="team")

    c.watch(Miss, missed, until=When.EOT, on=c.me, label=c.ref)


@power(
    "p13330",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an ally within 5 squares regains hit points or saves",
    on=[
        Trigger(Healed, ally_within(5), "an ally within 5 squares regains hit points"),
        Trigger(
            SavingThrow,
            both(ally_within(5), _made_it),
            "an ally within 5 squares succeeds on a saving throw",
        ),
    ],
)
def p13330(c: Cast) -> None:
    c.temp_hp(2 * c.int_mod, on=c.me)


@power(
    "p8237",
    level=6,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p8237(c: Cast) -> None:
    """"If you are not their nearest enemy" is settled once, when the power is
    used, and per watcher: nothing in `Cast` re-asks a condition like that as
    the board moves. Hitting anything ends the whole thing, which is the other
    half of the printed duration."""
    ours = [c.me, *c.allies()]
    held: list[Effect] = []
    for foe in c.enemies():
        nearest = min(ours, key=lambda a, f=foe: query.distance_between(c.world, f, a))
        if nearest != c.me:
            hidden = c.invisible(to=foe, on=c.me, until=When.ENCOUNTER)
            if hidden is not None:
                held.append(hidden)

    def spend(ev: Hit) -> None:
        if ev.attacker == c.me:
            for hidden in held:
                c.world.effects.end(hidden, c.ref)

    c.watch(Hit, spend, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p8238",
    level=6,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p8238(c: Cast) -> None:
    """Who is within 5 squares is settled each time the effect is sustained,
    which is as often as the printed line can be re-read.

    **"If you move, the effect ends" is written now.** The old note said
    "an effect cannot end itself here", and it can: the effect is held, a
    `Moved` watch on the caster calls `world.effects.end` on it, and the
    watch dies with it. #1341.

    `Moved` rather than `MoveStart`, so the effect survives a move that is
    declared and then cancelled -- the printed line is "if you move", and a
    cancelled move is not one.
    """

    def steady() -> None:
        c.immovable(on=c.me, until=When.EONT)
        for friend in c.within(5, of=c.me, side="ally"):
            if friend != c.me:
                c.immovable(on=friend, until=When.EONT)

    steady()
    held = c.effect(c.ref, on=c.me, until=When.SUSTAIN, sustain=MINOR)
    c.on_sustain(held, steady)

    def walked(ev: Moved) -> None:
        if ev.actor == c.me and held is not None:
            c.world.effects.end(held, "the psion moved")

    c.watch(Moved, walked, until=When.SUSTAIN, on=c.me, label=f"{c.ref} breaks")
