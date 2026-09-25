"""Sorcerer, level 2: utility.

**"Choose 1-10 or 11-20"** (p11832, and p11833 at level 6) takes the choice
blind and reads the face back off the log -- see `dice.py` for why waiting
for the roll is not on offer to a free action.

**A stance's rider** is `When.ENCOUNTER` and ended from the stance's own
`on_end`, because a second `When.STANCE` effect confuses `Effects.stance_of`
-- the arrangement `fighter/level_5_b.py` settled on.

Five rows of this level are left out; see the report and `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Event,
    Hit,
    Keyword,
    Trigger,
    TurnEnd,
    When,
    World,
    ally_within,
    both,
    by_me,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import DamageApplied, Miss

from .dice import face_of

ARCANE = [Keyword.ARCANE]

_I_MISSED = "you miss with a sorcerer attack power"
_ALLY_ATTACKS = "an ally within 10 squares makes an attack"
_HIT_BY_ANYTHING = "you are hit by an attack"
_ELEMENTAL_HURT = "you take cold, lightning or thunder damage"

#: The three types p3055 answers, and the keyword each of them rides under.
_STORM = {
    DamageType.COLD: Keyword.COLD,
    DamageType.LIGHTNING: Keyword.LIGHTNING,
    DamageType.THUNDER: Keyword.THUNDER,
}


def _my_sorcerer_attack(world: World, me: int, ev: Event) -> bool:
    """"You miss a target with a sorcerer attack power"."""
    if not by_me(world, me, ev):
        return False
    p = get(getattr(ev, "power", ""))
    return p is not None and p.cls == "sorcerer" and p.attack is not None


def _elemental_hit_me(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _STORM
    )


@power(
    "p11831",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_I_MISSED,
    on=Trigger(Miss, when=_my_sorcerer_attack, text=_I_MISSED),
)
def p11831(c: Cast) -> None:
    """`Miss` carries the live `AttackResult` and is emitted before the body
    that rolled it reads the answer, so a reroll here still changes what
    that body does.

    "You regain the use of this power at the start of your next turn" is not
    written: nothing refreshes a spent daily.
    """
    if not c.reroll_attack():
        return
    result = getattr(c.trigger, "result", None)
    if result is not None and not result.hit:
        c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=c.me)


@power(
    "p11832",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_ALLY_ATTACKS,
    on=Trigger(AttackDeclared, when=ally_within(10), text=_ALLY_ATTACKS),
)
def p11832(c: Cast) -> None:
    """Both halves land -- the bonus is +5 or +2, never nothing -- so this is
    one `bonus` call with two possible sizes rather than a +2 and a gated +3,
    which by the larger-wins rule would have come to +3.

    "Before the ally makes his or her first attack roll" cannot be honoured:
    a **free** action is offered in the `Window.AFTER` of the event it
    triggers on, and the whole attack -- roll, hit, damage -- resolves inside
    the `AttackDeclared` emit. So by the time this body runs the die is
    already down, and the face is read back off the log rather than waited
    for. The choice itself is still taken blind, which is the half of the
    sentence that is about this row.
    """
    swinger = getattr(c.trigger, "attacker", None)
    low = c.choose(["1-10", "11-20"], f"{c.ref}: which half of the die") == "1-10"
    face = face_of(c, swinger)
    if face is None:
        return
    inside = face <= 10 if low else face >= 11
    c.bonus("damage", 5 if inside else 2, on=c.me, until=When.EONT)


@power(
    "p16236",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p16236(c: Cast) -> None:
    held = c.stance(conditions=(Condition.SLOWED,), label=c.ref)
    shield = c.resist(c.cha_mod, on=c.me, until=When.ENCOUNTER)
    if shield is not None:
        held.on_end.append(lambda: c.world.effects.end(shield, "stance ended"))


@power(
    "p16237",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p16237(c: Cast) -> None:
    """The partial concealment is not written -- concealment is not modelled.
    The latch is per creature per round, which is what "only once per turn"
    means when several creatures share a round.
    """
    c.aura(1, label=c.ref, until=When.EONT)
    me, bite = c.me, c.cha_mod
    struck: dict[int, int] = {}

    def burn(who: int) -> None:
        if who == me or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(bite, dtype=DamageType.FIRE, on=who)

    def swung(ev: AttackDeclared) -> None:
        p = get(ev.power)
        if ev.target == me and p is not None and p.reach.kind == "melee":
            burn(ev.attacker)

    def stayed(ev: TurnEnd) -> None:
        if not ev.ghost and c.adjacent(ev.actor):
            burn(ev.actor)

    c.watch(AttackDeclared, swung, until=When.EONT, on=me, label=f"{c.ref} sears")
    c.watch(TurnEnd, stayed, until=When.EONT, on=me, label=f"{c.ref} lingers")


@power(
    "p16239",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p16239(c: Cast) -> None:
    """"One extra square for each square of movement **toward you**" is laid
    as plain difficult terrain: a zone charges the same for every direction
    and nothing reads which way a step was going. The lightly obscured half
    is concealment and is not modelled.
    """
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.EONT, difficult=True)


@power(
    "p3053",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=ARCANE,
)
def p3053(c: Cast) -> None:
    """The fall is not written: nothing drops a creature that ends a move in
    the air, and granting the mode for the move is what actually carries it.
    The caster is the other half of the printed target line and goes first.
    """
    if c.first:
        pace = c.speed_of() + 2
        c.mode("fly", pace, on=c.me, until=When.EOT)
        c.move(pace)
    friend = c.target
    if friend is None:
        return
    theirs = c.speed_of(friend) + 2
    c.mode("fly", theirs, on=friend, until=When.EOT)
    c.move(theirs, who=friend)


@power(
    "p3055",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_ELEMENTAL_HURT,
    on=Trigger(DamageApplied, when=_elemental_hit_me, text=_ELEMENTAL_HURT),
)
def p3055(c: Cast) -> None:
    """"Your next attack that deals the triggering damage type" is gated on
    the *power*, which is what the attack context carries -- there is no
    damage type in it, and the keyword is where a row's element lives."""
    kind = getattr(c.trigger, "dtype", None)
    if kind not in _STORM:
        return
    c.resist(c.cha_mod, kind, on=c.me, until=When.ENCOUNTER)
    word = _STORM[kind]

    def same_element(ctx: dict) -> bool:
        p = get(ctx.get("power", ""))
        return p is not None and word in p.keywords

    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER, kind="untyped",
        when=same_element, once=True,
    )


@power(
    "p3201",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p3201(c: Cast) -> None:
    c.teleport(max(1, c.speed_of() // 2))


@power(
    "p3207",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=ARCANE,
)
def p3207(c: Cast) -> None:
    """Heavily obscured is a zone that blocks line of sight. It is laid where
    the sorcerer stands and does not travel -- a zone has no anchor, and an
    aura cannot say it blocks sight."""
    area = c.area()
    if area:
        c.zone(
            area, label=c.ref, until=When.SUSTAIN,
            blocks_sight=True, sustain=MINOR,
        )


@power(
    "p3741",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
    trigger=_HIT_BY_ANYTHING,
    on=Trigger(AttackDeclared, when=both(hits_me), text=_HIT_BY_ANYTHING),
)
def p3741(c: Cast) -> None:
    """Declared on the announcement rather than on the landing: an interrupt
    runs before the roll is judged, which is the only window in which a
    defence bonus can affect the attack that provoked it."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 1, on=c.me, until=When.EONT)
    me = c.me

    def scorch(ev: Hit) -> None:
        p = get(ev.power)
        if ev.target == me and p is not None and p.reach.kind == "melee":
            c.flat(c.roll("1d6"), dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, scorch, until=When.EONT, on=me, label=f"{c.ref} flares")


@power(
    "p5268",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p5268(c: Cast) -> None:
    c.note(f"{c.ref}: +2 to one skill check this turn, which nothing rolls")
