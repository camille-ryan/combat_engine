"""Paladin, level 6: utility. Nothing here rolls an attack.

`p1289` is telepathy and a better aid-another bonus. Neither is a thing
this engine holds -- there is no channel to talk on and no check to aid --
so it is declared inert rather than given an invented effect.

`p356` is the one with teeth: a standing arrangement that takes half of an
ally's damage for the rest of the fight, written on `DamageRolled` in the
interrupt window, which is where the number still exists and has not yet
come off anybody.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    SELF,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Relation,
    Trigger,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import DamageRolled, EffectExpired
from combat_engine.engine.grid import spread
from combat_engine.engine.movement import walk
from combat_engine.engine.query import squares as squares_of

from .marks import burning_mark

DIVINE = [Keyword.DIVINE]
_DEFENCES = (AC, FORT, REF, WILL)


def _melee_at_will(ref: str) -> bool:
    p = get(ref or "")
    return (
        p is not None
        and p.usage is Usage.AT_WILL
        and p.reach.kind in ("melee", "close_burst", "close_blast")
    )


@power(
    "p10250",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p10250(c: Cast) -> None:
    """Stepping out of the stance is what pays, so the reward hangs on
    `EffectExpired` and reads its `why`: the deliberate drop is the only
    ending that says "ended deliberately", and an `on_end` callback is
    handed nothing to tell the two apart with.

    The watcher is armed on the encounter rather than on the stance -- an
    effect's own subscriptions are torn down before it announces its end.
    """
    me = c.me
    amount = 5 + max(c.wis_mod, c.cha_mod)
    st = c.stance(label=c.ref)
    st.drop_cost = FREE
    for dtype in (DamageType.COLD, DamageType.NECROTIC):
        warded = c.resist(amount, dtype, until=When.ENCOUNTER, on=me)
        if warded is not None:
            st.on_end.append(
                lambda held=warded: c.world.effects.end(held, "the stance ended")
            )
    tag = str(st)

    def stepped_out(ev: EffectExpired) -> None:
        if ev.what != tag or ev.why != "ended deliberately":
            return
        held = c.choose(list(_DEFENCES), "which defence the light holds")
        if held is not None:
            c.bonus(held, 2, on=me, until=When.EONT)

    c.watch(
        EffectExpired, stepped_out, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} parting gift",
    )


_MY_MISS = "you miss with a paladin encounter or daily attack power"


def _my_paladin_miss(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return (
        p is not None
        and p.cls == "paladin"
        and p.usage in (Usage.ENCOUNTER, Usage.DAILY)
    )


@power(
    "p11050",
    level=6,
    cls="paladin",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_MY_MISS,
    on=Trigger(Miss, when=_my_paladin_miss, text=_MY_MISS),
)
def p11050(c: Cast) -> None:
    """"The targets you missed" is one target here: a `Miss` is announced
    per target and the row is offered against the one that was announced,
    so the others are not in reach of this use.
    """
    missed = getattr(c.trigger, "target", None)
    if missed is not None:
        burning_mark(c, on=missed)
    c.bonus("damage", 2, on=c.me, until=When.EONT, kind="power", once=True)


@power(
    "p1279",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p1279(c: Cast) -> None:
    c.bonus("damage", c.cha_mod, until=When.ENCOUNTER)


@power(
    "p1289",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(6),
    target=EACH_ALLY,
    keywords=DIVINE,
    out_of_combat=True,
)
def p1289(c: Cast) -> None:
    c.note("p1289: the targets speak mind to mind out to 20 squares, and aid better")


@power(
    "p13560",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p13560(c: Cast) -> None:
    """The reduction is offered rather than taken: it is a free action the
    paladin may decline, and it costs five hit points each time.
    """
    friend = c.target
    if friend is None:
        return
    me = c.me
    for d in _DEFENCES:
        c.bonus(d, 2, on=friend, until=When.ENCOUNTER, kind="power")
    c.note(f"{c.ref}: +5 power bonus to the target's Endurance checks")

    def soak(ev: DamageRolled) -> None:
        if ev.target != friend or ev.amount <= 0:
            return
        if not c.may("take five of that", who=me):
            return
        ev.amount = max(0, ev.amount - 5)
        c.flat(5, on=me)

    c.watch(
        DamageRolled, soak, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} shelter",
    )


@power(
    "p13822",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FEAR],
)
def p13822(c: Cast) -> None:
    me = c.me

    def shove(ev: Hit) -> None:
        if ev.attacker == me and ev.target != me and _melee_at_will(ev.power):
            c.push(max(0, c.cha_mod), on=ev.target)

    c.watch(Hit, shove, until=When.ENCOUNTER, on=me, label=f"{c.ref} shove")


@power(
    "p13823",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[],
)
def p13823(c: Cast) -> None:
    """A rolled extra die, so it is `c.flat(c.roll(...))` rather than a
    damage modifier -- a modifier is a number and this is a weapon die.
    """
    me = c.me

    def bite(ev: Hit) -> None:
        if ev.attacker != me or ev.target == me:
            return
        p = get(ev.power or "")
        if p is None or p.reach.kind != "melee" or Keyword.WEAPON not in p.keywords:
            return
        if any(c.bloodied(who) for who in c.within(1, side="other")):
            c.flat(c.roll(c.w(1)), on=ev.target)

    c.watch(Hit, bite, until=When.ENCOUNTER, on=me, label=f"{c.ref} savagery")


@power(
    "p3285",
    level=6,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=DIVINE,
)
def p3285(c: Cast) -> None:
    """Which effect is being shaken off decides whether the bonus applies,
    so the save is rolled by hand: an effect's label opens with the ref that
    laid it, and that is where the fear keyword is.
    """
    who = c.target
    if who is None:
        return
    saves = [e for e in c.world.effects.of(who) if e.when is When.SAVE_ENDS and not e.ended]
    if not saves:
        c.note(f"{c.ref}: nothing a save can end")
        return
    shaken = c.choose(saves, "which effect is shaken off")
    if shaken is None:
        return
    p = get(shaken.label.split(" ")[0])
    if p is not None and Keyword.FEAR in p.keywords:
        shaken.save_mod += c.wis_mod
    c.world.effects.save(shaken)


@power(
    "p356",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE,
)
def p356(c: Cast) -> None:
    """Half of whatever the ally takes arrives here instead.

    Ending it deliberately is a free action, which is `drop_cost` on the
    effect the watcher lives on -- the same door `c.form` uses to let a
    shape be stepped out of.

    "No power or effect can reduce the damage you take from this power" has
    no spelling: the paladin's half goes through `deal_damage` like anything
    else, so resistance still reads it. The line is left unwritten rather
    than approximated with an immunity the row does not grant.
    """
    friend = c.target
    if friend is None:
        return
    me = c.me

    def share(ev: DamageRolled) -> None:
        if ev.target != friend or ev.amount <= 0:
            return
        half = ev.amount // 2
        ev.amount -= half
        if half:
            c.flat(half, dtype=ev.dtype, on=me)

    bond = c.watch(
        DamageRolled,
        share,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )
    bond.drop_cost = FREE


_ATTACKED = "an enemy attacks you"


@power(
    "p3748",
    level=6,
    cls="paladin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_ATTACKED,
    on=Trigger(AttackDeclared, when=targets_me, text=_ATTACKED),
)
def p3748(c: Cast) -> None:
    for d in (FORT, WILL):
        c.bonus(d, 4, on=c.me, until=When.EONT, kind="power")


@power(
    "p3751",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[*DIVINE, Keyword.RADIANT],
)
def p3751(c: Cast) -> None:
    """Hit or miss, so both are watched. "Unless that enemy is marked by the
    target" is the ally's own mark, not the paladin's.
    """
    friend = c.target
    if friend is None:
        return
    me, amount = c.me, 3 + c.cha_mod

    def sear(ev: Hit | Miss) -> None:
        foe = ev.attacker
        if ev.target != friend or foe in (friend, me):
            return
        if c.world.relations.holds(Relation.MARKED_BY, friend, foe):
            return
        c.flat(amount, dtype=DamageType.RADIANT, on=foe)

    for kind in (Hit, Miss):
        c.watch(kind, sear, until=When.ENCOUNTER, on=me, label=f"{c.ref} ward")


@power(
    "p7255",
    level=6,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p7255(c: Cast) -> None:
    c.resist(max(0, c.str_mod), until=When.EONT, on=c.me)


@power(
    "p7256",
    level=6,
    cls="paladin",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p7256(c: Cast) -> None:
    """The destination is named by the printed line -- next to an enemy it
    can see -- so the pool is filtered before the choice rather than handed
    to the decider whole, which with nobody deciding takes the lowest square
    on the board and runs away from everybody.
    """
    paths = c.world.reachable_paths(c.me, 2 * c.speed_of())
    seen = [f for f in c.enemies() if c.can_see(f)]
    beside = {sq for f in seen for sq in spread(squares_of(c.world, f), 1)}
    options = sorted(sq for sq, path in paths.items() if sq in beside and path)
    if not options:
        return
    dest = c.choose(options, "where the run ends")
    if dest is not None:
        walk(c.world, c.me, list(paths[dest]))


_MY_MARK_HITS_ME = "the creature you marked hits you"


def _my_mark_hits_me(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and foe is not None
        and world.relations.holds(Relation.MARKED_BY, me, foe)
    )


@power(
    "p7382",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[*DIVINE, Keyword.HEALING],
    trigger=_MY_MARK_HITS_ME,
    on=Trigger(Hit, when=_my_mark_hits_me, text=_MY_MARK_HITS_ME),
)
def p7382(c: Cast) -> None:
    """Declared on the hit itself, in the interrupt window, which is before
    the body of the attack rolls its damage -- so the surge is spent against
    a blow that has not landed yet, as the printed trigger reads.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT, kind="power",
        when=lambda ctx: ctx.get("target") == foe,
    )
