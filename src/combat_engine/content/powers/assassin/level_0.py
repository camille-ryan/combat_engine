"""Assassin, level 0: the class features and the weapon at-wills.

Two things recur and are worth saying once.

* **The weapons are in the table now, and this said they were not.** Garrote,
  bola, blowgun, hand crossbow, shuriken and kusari-gama were all absent when
  that was written, so a `requires=` gate would have been false forever and the
  rows carried the printed line as `requires_text` alone. Every one of the six
  has an entry today -- checked, all seven including the short sword -- so the
  reason had outlived itself and the rows were displaying a requirement they did
  not apply. They are gated by ref through `_wielding` below. #236.
* **Assassin poisons are items.** Every "if you deliver an assassin poison"
  clause is about a consumable smeared on the blade, which nothing models,
  so those sentences are dropped rather than approximated.

The shroud is a counter rather than a stack of effects: the count is the only
thing anything reads, and a count can be cleared in one line when the shrouds
are invoked, which a set of modifiers cannot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DEX,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Effect,
    Escaped,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Trigger,
    UpTo,
    Usage,
    When,
    World,
    both,
    by_me,
    get,
    power,
)
from combat_engine.engine.query import adjacent, creatures, distance_between

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

SHROUD_MAX = 4


def _wielding(name: str):  # noqa: ANN202
    """A `requires=` gate on holding one named weapon.

    **These rows displayed a requirement they did not apply.** `usable` returns
    `requires_text` only as the words a refusal prints; with no `requires` beside
    it the card said "you must be wielding a garrote" and the row was offered to
    anybody. #236.

    `query.holding` matches by ref as well as by group, which is what makes this
    one line: a garrote has no group of its own and a short sword shares `light
    blade` with thirteen other things, so the group is not the question.
    """
    from combat_engine.engine.query import holding

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, name))

    return gate


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.group == "light blade"


def _beside_a_creature(world: World, eid: int) -> bool:
    return any(who != eid and adjacent(world, eid, who) for who in creatures(world))


def _struck_with_a_weapon(squares: int) -> Callable[[World, int, Event], bool]:
    """Hit a creature within N squares of me, with something that is a
    weapon rather than an implement."""

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        if who is None or distance_between(world, me, who) > squares:
            return False
        p = get(getattr(ev, "power", "") or "")
        return p is not None and Keyword.WEAPON in p.keywords

    return check


def _ends_on_my_attack(c: Cast, effects: list[Effect | None]) -> None:
    """"The form lasts until you make an attack roll", which no duration
    says: the effects are ended by hand off my own next roll."""

    def stop(ev: AttackRolled) -> None:
        if ev.attacker != c.me:
            return
        for eff in effects:
            if eff is not None:
                c.world.effects.end(eff)

    c.watch(AttackRolled, stop, until=When.EONT, on=c.me, label=f"{c.ref} ends")


def _killed_beside_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return (
        getattr(ev, "source", None) == me and who is not None and adjacent(world, me, who)
    )


# -- the features ----------------------------------------------------------


@power(
    "p9400",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW],
    once_per_round=True,
)
def p9400(c: Cast) -> None:
    """Invoking is armed once as a watch on my own attacks against whoever
    currently carries the shrouds: hit or miss the dice land, one die fewer
    on a miss, and the count clears.

    **The printed "all or none" choice is asked now, and the note that used
    to say it never needed asking was true only in isolation.** It read
    *"the printed choice is always taken -- declining wins nothing and
    costs the shrouds nothing"*, which was right about this row alone and
    wrong about the class: `p9405` prints *"if you didn't invoke your
    shrouds on the target, it takes 1 extra damage for each of your
    shrouds on it"*, so declining pays. With the choice hard-wired that
    row's whole clause was unreachable -- it looked at a count this watch
    had already zeroed, measured at 0 every time.

    `c.may` is the ask, and it is asked **before the roll** as the card
    says -- *"before you make an attack roll ... you choose"* -- which is
    `Window.BEFORE` on the watch. With no policy installed `c.may` takes
    its default, so the engine keeps invoking and nothing about today's
    behaviour moves; a policy that declines now has somewhere to say so.

    The count itself is `c.shroud`/`c.shrouds`, so a later row reading "for
    each shroud on that enemy" has something to ask; it is cleared **after**
    the damage rather than before, so that question is still answerable from
    inside the blow the shrouds paid for."""
    victim = c.target
    if victim is None:
        return
    c.shroud(on=victim, cap=SHROUD_MAX)
    # The count lives on the creature as a `Shrouds` component; this is only
    # the once-per-fight arming flag, so that a second encounter arms its own
    # watch. It was a module dict keyed on `id(c.world)`, which is the bug
    # `World.latches` is about -- and this row is where it was found.
    if not c.once_per_board(c.me):
        return
    per = 0 if c.level < 11 else (3 if c.level < 21 else 6)

    def invoke(ev: Any) -> None:
        if ev.attacker != c.me or c.shrouds(ev.target) <= 0:
            return
        # **The printed choice, all or none.** `p9405` rewards declining,
        # so this cannot be hard-wired -- see the docstring.
        if not c.may("invoke your shrouds"):
            return
        count = c.shrouds(ev.target) - (1 if isinstance(ev, Miss) else 0)
        if count > 0:
            # **Per shroud**, which is why the face is read and the count is
            # not. f3638 raises the die each shroud is worth; how many there
            # are is the board's business and no feat's.
            face = c.dice_for(c.ref, "1d6").split("d")[-1]
            c.flat(c.roll(f"{count}d{face}") + count * per, on=ev.target)
        # **`f3636`'s clause, written here per #550.** It keeps the count
        # on the target when the blow that invoked them was a critical hit
        # with a shadow power. The event answers both halves -- `Miss`
        # carries no `critical` at all, so a miss never reaches it -- and
        # the keyword is the attacking row's, not this feature's.
        aimed = get(ev.power)
        if (
            getattr(ev, "critical", False)
            and aimed is not None
            and Keyword.SHADOW in aimed.keywords
            and c.feat("f3636")
        ):
            return
        c.spend_shrouds()

    c.watch(Hit, invoke, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} shrouds")
    c.watch(Miss, invoke, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} shrouds")


@power(
    "p9401",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    requires=_beside_a_creature,
    requires_text="must be adjacent to a creature",
)
def p9401(c: Cast) -> None:
    """"To a square adjacent to a different creature" is a constraint on the
    destination and `c.teleport` has no way to carry one, so the square is
    left to the world's decider.

    Through `c.instead_of` so that `f2831` can replace the distance
    outright. The printed clause is the `default`, so the row is unchanged
    for anybody with nothing registered."""
    # Read rather than written in, so `f2935` can lengthen it. #502.
    c.instead_of("teleport", lambda: c.teleport(
        c.squares_for(c.ref, 3 if c.level < 11 else (4 if c.level < 21 else 5))
    ))


@power(
    "p9402",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9402(c: Cast) -> None:
    """The Stealth half is narrative.

    **Sustain Minor is written now, and "not written" understated what
    was available.** A sustain cost is stored beside an effect and 118
    content sites already pass `sustain=MINOR`; what neither
    `c.insubstantial` nor `c.vulnerable` takes is the cost itself, so
    the form is carried by a hold that does and the two riders are tied
    to it. #1341.

    That is the arrangement `p13793`'s garrote uses for Sustain Standard,
    and it is the only one that keeps the card's three clocks straight:
    the form ends when the assassin attacks, at the end of its next turn
    **or** when it stops paying -- whichever the fight reaches first, and
    sustaining pushes only the second of the three.
    """
    form = c.effect(
        f"{c.ref} shadowy form", until=When.SUSTAIN, on=c.me, sustain=MINOR
    )
    thin = c.insubstantial(until=When.SUSTAIN, on=c.me)
    weak = c.vulnerable(5, DamageType.RADIANT, until=When.SUSTAIN, on=c.me)
    if form is not None:
        form.on_end.append(
            lambda: [
                c.world.effects.end(e)
                for e in (thin, weak)
                if e is not None
            ]
        )
    _ends_on_my_attack(c, [form, thin, weak])


@power(
    "p13799",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you hit a creature within 5 squares of you with a weapon attack",
    on=Trigger(
        Hit,
        both(by_me, _struck_with_a_weapon(5)),
        "you hit a creature within 5 squares of you with a weapon attack",
    ),
)
def p13799(c: Cast) -> None:
    """The victim is read off the triggering `Hit` rather than targeted: the
    row is Personal and the printed target is "the creature you hit"."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    dice = 1 + sum(c.level >= n for n in (3, 7, 13, 17, 23, 27))
    if c.is_(Condition.HELPLESS, on=victim):
        c.flat(dice * 10, on=victim)
    else:
        c.damage(f"{dice}d10", on=victim)


@power(
    "p14372",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you hit a creature within 5 squares of you with a weapon attack",
    on=Trigger(
        Hit,
        both(by_me, _struck_with_a_weapon(5)),
        "you hit a creature within 5 squares of you with a weapon attack",
    ),
)
def p14372(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    dice = 1 + (c.level >= 11) + (c.level >= 21)
    if c.is_(Condition.HELPLESS, on=victim):
        c.flat(dice * 10, on=victim)
    else:
        c.damage(f"{dice}d10", on=victim)


@power(
    "p14399",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.FIRE, Keyword.NECROTIC],
)
def p14399(c: Cast) -> None:
    """"Fire and necrotic damage" is one number of two types and `c.flat`
    takes **`dtypes`** for exactly this -- "one blow of several types" -- so
    it lands as both now. The old note said the verb took one type and that
    the alternative was dealing it twice, which would indeed have doubled
    the row; `dtypes` is the third option neither half considered, and it is
    the fourth time this class of claim has been wrong in this tree. #1341.

    The free shroud that comes with the form is still dropped, and the
    reason is unchanged and correct: it is a rule about another power's
    usage limit -- "does not count against the limit on the number of times
    per round" -- not an effect. Shrouds themselves **are** modelled
    (`c.shroud`, `c.shrouds`, `c.spend_shrouds`); the per-round limit is
    what has no door."""
    amount = 5 if c.level < 11 else (10 if c.level < 21 else 15)
    armour = c.resist(amount, until=When.EONT, on=c.me)

    def retaliate(ev: Hit) -> None:
        p = get(getattr(ev, "power", "") or "")
        if ev.target != c.me or p is None or p.reach is None or p.reach.kind != "melee":
            return
        c.flat(
            amount,
            dtypes=(DamageType.FIRE, DamageType.NECROTIC),
            on=ev.attacker,
            from_attack=False,
        )

    watcher = c.watch(Hit, retaliate, until=When.EONT, on=c.me)
    _ends_on_my_attack(c, [armour, watcher])


# -- the weapon at-wills ----------------------------------------------------


@power(
    "p13793",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_wielding("garrote"),
    requires_text="must use a garrote, against a creature you are hidden from",
)
def p13793(c: Cast) -> None:
    """The grab is held on a named effect rather than on `c.grab`, because
    only an effect can carry the printed Sustain Standard and its payout.
    **"You cannot make other attacks" is written now**, and "has no
    `Cast` method" was false: `c.forbid(attacks_only=True)` is that
    sentence, and its own docstring calls `attacks_only` "that second
    card's narrowing". #1341.

    It lands `on=c.me` -- the assassin is the one whose hands are full --
    and `c.forbid` takes its creature from `_who`, which defaults to the
    **target**, so omitting it would have barred the victim's attacks
    instead. That is the same default `c.flat`, `c.temp_hp` and
    `c.hover` have.

    It rides the garrote hold rather than a clock of its own, because the
    printed scope is "while the grab persists" -- so letting the grab go
    frees the hands in the same moment.

    "Cannot speak" is still dropped and is still not a combat effect."""
    c.shift(2)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.dex_mod)
    c.grab(on=victim)
    c.penalty(
        "attack",
        -2,
        until=When.EONT,
        on=victim,
        when=lambda ctx: ctx.get("target") == c.me,
    )
    hold = c.effect(f"{c.ref} garrote", until=When.SUSTAIN, on=victim, sustain=STANDARD)
    c.on_sustain(hold, lambda: c.damage(c.w(2), c.dex_mod, on=victim))
    # **`usage=` is required and `attacks_only=` alone bars nothing.**
    # That flag narrows a usage list rather than standing on its own --
    # measured, the first draft left the assassin's basic attack usable --
    # and "you cannot make OTHER attacks" is every category at once, so
    # all four are named.
    busy = c.forbid(
        usage=(Usage.AT_WILL, Usage.ENCOUNTER, Usage.DAILY, Usage.RECHARGE),
        attacks_only=True,
        on=c.me,
        until=When.SUSTAIN,
    )
    if hold is not None and busy is not None:
        hold.on_end.append(lambda: c.world.effects.end(busy, "grab ended"))


@power(
    "p13794",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_wielding("dagger"),
    requires_text="must use a dagger",
)
def p13794(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p13795",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p13795(c: Cast) -> None:
    """"Shift back to your starting position" names the square outright, so
    the square is remembered before the first shift and handed to `to=`."""
    start = c.here
    c.shift(1)
    if c.strike():
        c.damage(c.w())
        c.prone()
        c.shift(1, to=start)


@power(
    "p13796",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_wielding("bola"),
    requires_text="must use a bola",
)
def p13796(c: Cast) -> None:
    if c.strike():
        c.damage(c.w())
        c.prone()


@power(
    "p13797",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_wielding("blowgun"),
    requires_text="must use a blowgun",
)
def p13797(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p13798",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    no_provoke=True,
    requires=_wielding("hand crossbow"),
    requires_text="must use a hand crossbow",
)
def p13798(c: Cast) -> None:
    """Range 1 is what the entry prints, odd as it looks for a crossbow."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)
    c.shift(2)


@power(
    "p13806",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a hand free and a light blade",
)
def p13806(c: Cast) -> None:
    """**The escape penalty is written now.** The old note said "escaping a
    grab is rolled inside the engine and nothing can put a number on that
    one attempt", and both halves of that are answered: `"escape"` is one
    of `c.penalty`'s words with fourteen callers and `escape.attempt`
    reads it. #1341.

    **"First" is ended by hand, because `once=True` refuses here and the
    refusal is right.** `c.bonus` raises for `'escape'` with the reason
    spelled out: the key has no spend moment, so `once=` would be consumed
    by the next *attack* roll instead -- "which is the bug this refusal
    replaces". So the penalty is laid plain and dropped on the first
    `Escaped`, which the engine emits for a failed attempt as well as a
    successful one, gated on `holder` being this grabber.

    Still dropped, and this half the old note had right: the clause letting
    a missed swing spend `p13799` is a rule about another row's usage
    limit rather than an effect, so it carries the marker.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w())
    c.grab(on=victim)
    c.grants_advantage(until=When.EONT, on=victim, to="team")
    first = c.penalty("escape", 2, on=victim, until=When.EONT)
    if first is not None:

        def spent(ev: Escaped) -> None:
            if ev.actor == victim and ev.holder == c.me:
                c.world.effects.end(first, "the first escape attempt is past")

        first.subs.append(c.world.bus.on(Escaped, spent))
    hold = c.effect(f"{c.ref} hold", until=When.SUSTAIN, on=victim, sustain=MINOR)
    c.on_sustain(hold, lambda: c.grab(on=victim))

    # *"If you make a melee weapon attack against the target before the
    # grab ends and your `p13799` is not expended, you can use that power
    # against the target even if the attack misses."*
    #
    # **`f2793b`'s pattern**: declare the wider moment here and spend the
    # borrowed row, rather than editing `p13799`'s own trigger -- which is
    # `Hit` and right for that card. `c.use_power` passes `c.trigger`
    # through, and `p13799`'s body reads its victim off it, so the `Miss`
    # is what it is handed.
    #
    # *"not expended"* needs no test: `c.use_power` spends by default and
    # answers False when the row is already gone, which is the printed
    # limit and not this row's.
    if hold is not None:

        def missed(ev: Miss) -> None:
            if getattr(ev, "attacker", None) != c.me or ev.target != victim:
                return
            # No `hold.ended` test: *"before the grab ends"* is carried by
            # the subscription, not by a guard. `Effects.end` calls
            # `bus.off` on every entry in `subs`, and the dispatch loop
            # re-checks membership for a sub an earlier listener removed --
            # so this handler cannot run after the grab goes. A guard here
            # read as the enforcement and was unreachable: the plant that
            # deletes it passes.
            swung = get(getattr(ev, "power", "") or "")
            # "a melee weapon attack", both words. A ranged miss or an
            # unarmed one is not what the clause names.
            if swung is None or Keyword.WEAPON not in swung.keywords:
                return
            if getattr(swung.reach, "kind", "") != "melee":
                return
            if not c.may("spend p13799 on the miss"):
                return
            # **The miss has to be handed over as the trigger**, which is
            # the half `f2793b` gets for free and this row does not.
            # `c.use_power` passes `c.trigger` through, `p13799`'s body
            # reads its victim off it -- and `p13806` is a standard action
            # with no trigger of its own, so the borrowed row was handed
            # `None` and returned at its first line. `on=` does not help:
            # that card reads the trigger, not `c.target`.
            #
            # Put back afterwards, because this `Cast` outlives the handler
            # -- the watch fires again on the next miss while the grab
            # holds, and a leaked trigger would be read as that one's.
            #
            # **Defensive, and no fixture reds it**: the next miss assigns
            # `c.trigger` before reading it, and the row's other two
            # closures (`c.on_sustain`, the `Escaped` watch) do not read
            # it at all. Kept as discipline around a borrowed mutable
            # rather than claimed as load-bearing -- deleting the restore
            # passes `drivers.grab_widens`.
            was, c.trigger = c.trigger, ev
            try:
                c.use_power("p13799", on=victim)
            finally:
                c.trigger = was

        hold.subs.append(c.world.bus.on(Miss, missed))


@power(
    "p15911",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_wielding("short sword"),
    requires_text="must use a short sword",
)
def p15911(c: Cast) -> None:
    """"If you have jumped, fallen, or flown this turn" has nothing to ask --
    none of the three is kept -- so the conditional combat advantage is
    dropped. The charge clause is a substitution rule, not an effect."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p15912",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=UpTo(3),
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_wielding("shuriken"),
    requires_text="must use shuriken",
)
def p15912(c: Cast) -> None:
    if c.strike():
        c.damage(c.w())


@power(
    "p15913",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires_text="must use a kusari-gama",
)
def p15913(c: Cast) -> None:
    """The second end of the weapon is a secondary attack against the same
    creature, rolled by hand because the header holds one attack line.

    **The primary's zero-dice damage stays `c.damage`, not `c.flat`.** The
    modifier is printed on the `Hit:` line of a weapon attack, so it *is*
    that attack's damage roll, and a magic weapon adds its plus to the
    damage roll of every attack made with it whether or not the expression
    carries weapon dice. `c.flat` is for a bare quantity dealt outside a
    damage roll, as `f2478` deals on a *miss*. Both ends are swings of the
    same weapon, so both pay it. #1225.
    """
    if not c.strike():
        return
    c.damage(0, c.dex_mod)
    c.prone()
    c.shift(1)
    if c.attack(c.dex_, AC):
        c.damage(c.w())


@power(
    "p13813",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    trigger="you kill an adjacent creature",
    on=Trigger(Dropped, _killed_beside_me, "you kill an adjacent creature"),
    out_of_combat=True,
)
def p13813(c: Cast) -> None:
    """The corpse is already off the board; trapping it in a trinket changes
    nothing in the fight, so the row is deliberately inert."""
    c.note(f"{c.ref}: the corpse is trapped in a small object you carry")
