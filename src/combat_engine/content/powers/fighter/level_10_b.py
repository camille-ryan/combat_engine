"""Fighter, level 10: the utilities the later books added.

Nothing here rolls a declared attack line; the one that swings rolls its own.

**Cover** is not something an effect can grant -- `query.cover_between` reads
the grid and nothing else -- so "you gain cover" and "your allies have cover"
are written as what cover *is* in the rules it comes from: +2 to AC and
Reflex, under a `kind` of its own so two sources do not stack into four.

**"No Action"** has no bus window (`triggers.WINDOW_OF` has no entry for
`ActionType.NONE`), so those rows are declared as the window each needs.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
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
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageType,
    Effect,
    Health,
    Keyword,
    Melee,
    Relation,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_ranged,
    leaves_me_out,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    AttackDeclared,
    DamageRolled,
    ForcedMove,
    Hit,
    SurgeSpent,
)
from combat_engine.engine.query import defence

from .footwork import aura_ring, close_by_shift
from .grips import hand_free, has_shield

MARTIAL = [Keyword.MARTIAL]

#: The five the eladrin ward names.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)
_HELD_AT_DAWN = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)
_IGNORED = (Condition.DAZED, Condition.IMMOBILIZED, Condition.SLOWED, Condition.WEAKENED)


def _bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _hit_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me


def _would_hit_me(world: World, me: int, ev: Any) -> bool:
    result = getattr(ev, "result", None)
    return getattr(ev, "target", None) == me and bool(result and result.hit)


def _hurt_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "amount", 0) > 0


def _burned_me(world: World, me: int, ev: Any) -> bool:
    return _hurt_me(world, me, ev) and getattr(ev, "dtype", None) in _ELEMENTS


def _shoved_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me


def _floored_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "condition", None) is (
        Condition.PRONE
    )


def _held_at_dawn(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "actor", None) != me or getattr(ev, "ghost", False):
        return False
    return any(
        effect.when is When.SAVE_ENDS
        and any(card in _HELD_AT_DAWN for card in effect.conditions)
        for effect in world.effects.of(me)
    )


def _burning_at_dawn(world: World, me: int, ev: Any) -> bool:
    """"You take ongoing damage at the start of your turn." The effects clock
    deals it with the effect's own description as the detail."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and "ongoing" in getattr(ev, "detail", "")
    )



def _ranged_hit_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and by_ranged(world, me, ev)


_I_AM_HIT = "you are hit by an attack"
_MELEE_OR_RANGED_HIT = "an enemy hits you with a melee or a ranged attack"
_I_TAKE_DAMAGE = "you take damage"
_ELEMENTAL_DAMAGE = "you take acid, cold, fire, lightning or thunder damage"
_SHOVED_OR_FLOORED = "you are pulled, pushed, slid or knocked prone"
_HELD_AT_DAWN_TEXT = "you start your turn dazed, dominated or stunned by something a save can end"
_BURNING_AT_DAWN = "you take ongoing damage at the start of your turn"
_RANGED_HIT_ME = "a ranged attack hits you"


# -- stances ----------------------------------------------------------------


@power(
    "p10337",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10337(c: Cast) -> None:
    """Standing in front of everybody: the allies beside the fighter get the
    cover, and the fighter gets swung at with the gloves off.

    The opening is handed out from each attack's own declaration, which is
    the last moment it can be given and still be read -- a relation set now
    would name only the enemies already on the board.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    aura_ring(
        c, stance, side="ally",
        give=lambda who: [
            c.bonus(AC, 2, on=who, until=When.ENCOUNTER, kind="cover"),
            c.bonus(REF, 2, on=who, until=When.ENCOUNTER, kind="cover"),
        ],
    )

    def offer(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me:
            c.grants_advantage(on=me, to=ev.attacker, until=When.EOT)

    held = c.watch(
        AttackDeclared, offer, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} wide open",
    )
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p10514",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10514(c: Cast) -> None:
    """Nothing marks an attack as unarmed -- the damage context names the row
    and not the hand -- so the gate is what is in the fighter's hands, which
    is what makes an attack unarmed in the first place. See the report.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    rider = c.bonus(
        "damage", max(1, c.dex_mod), on=me, until=When.ENCOUNTER,
        when=lambda _ctx: c.wielding("unarmed"),
    )
    if rider is not None:
        stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))


@power(
    "p10515",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10515(c: Cast) -> None:
    """The restraint hangs on the grab's own effect, so letting go ends it
    and there is one thing to save against rather than two."""
    me = c.me
    stance = c.stance(label=c.ref)

    def pin(held: Effect, who: int) -> None:
        tighter = c.condition(Condition.RESTRAINED, until=When.ENCOUNTER, on=who)
        if tighter is not None:
            held.on_end.append(lambda: c.world.effects.end(tighter, "the grip opened"))

    def caught(ev: ConditionApplied) -> None:
        if ev.source != me or ev.condition is not Condition.GRABBED:
            return
        for effect in c.world.effects.of(ev.target):
            if Condition.GRABBED in effect.conditions and effect.source == me:
                pin(effect, ev.target)
                return

    for who in c.world.relations.targets(Relation.GRABBED_BY, me):
        for effect in c.world.effects.of(who):
            if any(k is Relation.GRABBED_BY and s == me for k, s, _t in effect.relations):
                pin(effect, who)

    watcher = c.watch(ConditionApplied, caught, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(watcher, "stance ended"))


@power(
    "p2229",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p2229(c: Cast) -> None:
    """"An attack that doesn't include you as a target" is judged over the
    whole attack with `leaves_me_out`, not off one announcement -- a burst
    that caught the fighter would otherwise pay out off another target."""
    me = c.me
    stance = c.stance(label=c.ref)

    def expose(ev: AttackDeclared) -> None:
        foe = ev.attacker
        if foe == me or not c.world.relations.holds(Relation.MARKED_BY, me, foe):
            return
        if not leaves_me_out(c.world, me, ev):
            return
        for friend in c.allies():
            if friend != me:
                c.grants_advantage(on=foe, to=friend, until=When.SOTNT)

    held = c.watch(
        AttackDeclared, expose, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p4334",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    requires=has_shield,
    requires_text="needs a shield",
)
def p4334(c: Cast) -> None:
    """Behind the shield and going nowhere. Cover is written as the +2 to AC
    and Reflex it is, because nothing can grant the grid's kind."""
    me = c.me
    stance = c.stance(conditions=[Condition.SLOWED], label=c.ref)
    for guard in (AC, REF):
        rider = c.bonus(guard, 2, on=me, until=When.ENCOUNTER, kind="cover")
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


# -- minor and move actions -------------------------------------------------


@power(
    "p10000",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p10000(c: Cast) -> None:
    """The first surge is this row's; every one after it for the rest of the
    fight buys the same thing, which is what the watcher is for."""
    me = c.me

    def rally() -> None:
        for guard in (AC, FORT, REF, WILL):
            c.bonus(guard, 2, on=me, until=When.EONT)
        c.bonus("attack", 1, on=me, until=When.EONT)

    if c.may("spend a surge", who=me):
        c.surge(on=me)
    rally()

    def again(ev: SurgeSpent) -> None:
        if ev.actor == me:
            rally()

    c.watch(SurgeSpent, again, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p10512",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10512(c: Cast) -> None:
    """"You ignore the effects of" is not "the conditions end": the holds
    stay and are saved against as usual, and only the counts that make them
    bite are set aside, to be put back when the duration runs out.
    """
    from combat_engine.engine import Conditions

    conds = c.world.get(c.me, Conditions)
    hold = c.effect("shrugging it off", until=When.EONT, on=c.me)
    if conds is None or hold is None:
        return
    shelved = {card: conds.counts.pop(card) for card in _IGNORED if conds.counts.get(card)}

    def restore() -> None:
        for card, n in shelved.items():
            conds.counts[card] = conds.counts.get(card, 0) + n

    hold.on_end.append(restore)
    c.note(f"{c.ref}: ignoring {len(shelved)} condition(s)")


@power(
    "p10516",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p10516(c: Cast) -> None:
    """A bonus to an Intimidate or Streetwise check, and the engine rolls
    neither."""


@power(
    "p12678",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p12678(c: Cast) -> None:
    """"You or one ally": the ally pool already has the caster in it."""
    who = c.target
    if who is not None and c.may("spend a surge", who=who):
        c.surge(on=who)


@power(
    "p12679",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12679(c: Cast) -> None:
    for guard in (AC, FORT, REF, WILL):
        c.bonus(guard, 2, on=c.me, until=When.EONT)
    close_by_shift(c, c.speed_of())


@power(
    "p12681",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
)
def p12681(c: Cast) -> None:
    """"Until it hits or misses you" is the one-shot form of the grant, which
    is what `once` means -- spent by the first attack that could use it."""
    c.grants_advantage(to=c.me, until=When.EONT, once=True)


@power(
    "p12703",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
)
def p12703(c: Cast) -> None:
    """The Will ceiling is a narrowing of the Target line the header cannot
    hold, so it is asked per target here."""
    victim = c.target
    if victim is None or defence(c.world, victim, WILL) > 12 + c.level:
        return
    if c.may("shove it back", who=c.me):
        c.push(1)


@power(
    "p2005",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p2005(c: Cast) -> None:
    if c.may("spend a surge", who=c.me):
        c.surge(on=c.me)
    c.bonus(AC, max(1, c.dex_mod), on=c.me, until=When.SONT)


@power(
    "p4335",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p4335(c: Cast) -> None:
    """"Until you are no longer bloodied" is a second ending on the clock, so
    it is watched rather than timed. The Athletics and Endurance halves are
    skill checks the engine does not roll; the dragonborn line is a race it
    does not have. Both are in the report.
    """
    me = c.me
    rider = c.bonus(
        "damage", 4, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _is_melee(ctx),
    )
    if rider is None:
        return

    def mended(ev: Any) -> None:
        if ev.target == me and not _bloodied(c.world, me):
            c.world.effects.end(rider, "no longer bloodied")

    from combat_engine.engine.events import Healed

    rider.subs.append(c.world.bus.on(Healed, mended, owner=me))


def _is_melee(ctx: dict[str, Any]) -> bool:
    """The damage context carries no reach, so the row that dealt it is
    asked -- which is what `AUTHORING.md` says to do here."""
    from combat_engine.engine import get

    dealt = get(ctx.get("power", "") or "")
    return dealt is not None and dealt.reach.kind in ("melee", "close_burst", "close_blast")


@power(
    "p7391",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=has_shield,
    requires_text="needs a shield",
)
def p7391(c: Cast) -> None:
    """A shield bonus for whoever stands with the fighter, and the fighter
    swings harder for having company -- which is asked when the roll is
    made, not now."""
    me = c.me
    hold = c.effect("shoulder to shoulder", until=When.EONT, on=me)
    if hold is None:
        return
    aura_ring(
        c, hold, side="ally",
        give=lambda who: [
            c.bonus(AC, 2, on=who, until=When.ENCOUNTER, kind="shield"),
            c.bonus(REF, 2, on=who, until=When.ENCOUNTER, kind="shield"),
        ],
    )
    c.bonus(
        "attack", 2, on=me, until=When.EONT,
        when=lambda ctx: _is_melee(ctx)
        and any(a != me for a in c.within(1, of=me, side="ally")),
    )


# -- answering something ----------------------------------------------------


@power(
    "p10513",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=hand_free,
    requires_text="needs a hand free",
    trigger=_MELEE_OR_RANGED_HIT,
    on=Trigger(AttackRolled, _would_hit_me, _MELEE_OR_RANGED_HIT),
)
def p10513(c: Cast) -> None:
    """Somebody else is pulled into the path of the blow. The target is not
    whoever swung, which is what the dispatcher would aim this at, so the
    row takes none in the header and picks one here.
    """
    ev = c.trigger
    swinging = getattr(ev, "attacker", None)
    me = c.me
    pool = sorted(e for e in c.within(1, side="enemy") if e != swinging)
    shield = c.choose(pool, "who is pulled into it") if pool else None
    if shield is None or not c.attack(c.str_, REF, on=shield):
        return
    c.grab(on=shield)

    def split(blow: DamageRolled) -> None:
        if blow.source != swinging or blow.target != me or blow.amount <= 0:
            return
        half = blow.amount // 2
        blow.amount -= half
        if half:
            c.flat(half, dtype=blow.dtype, on=shield)

    c.watch(
        DamageRolled, split, until=When.EOT, window=Window.BEFORE, on=me, once=True,
        label=f"{c.ref} shared",
    )


@power(
    "p12680",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_TAKE_DAMAGE,
    on=Trigger(DamageRolled, _hurt_me, _I_TAKE_DAMAGE),
)
def p12680(c: Cast) -> None:
    ev = c.trigger
    if ev is None:
        return
    spared = ev.amount - ev.amount // 2
    ev.amount -= spared
    c.note(f"{c.ref}: {spared} damage turned aside")


@power(
    "p12702",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HELD_AT_DAWN_TEXT,
    on=Trigger(TurnStart, _held_at_dawn, _HELD_AT_DAWN_TEXT),
)
def p12702(c: Cast) -> None:
    """The save is aimed: `c.save` takes whichever save-ends effect it finds
    first, and the printed line names three conditions."""
    for effect in c.world.effects.of(c.me):
        if effect.when is When.SAVE_ENDS and any(
            card in _HELD_AT_DAWN for card in effect.conditions
        ):
            effect.save_mod += 5
            c.world.effects.save(effect)
            return


@power(
    "p12704",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_SHOVED_OR_FLOORED,
    on=(
        Trigger(ForcedMove, _shoved_me, "you are pulled, pushed or slid"),
        Trigger(ConditionApplied, _floored_me, "you are knocked prone"),
    ),
)
def p12704(c: Cast) -> None:
    """Four printed triggers, two events. `ForcedMove` is read back by the
    mover, so refusing it works; `ConditionApplied` is announced *after* the
    condition has been added, so the hold that put the fighter down is ended
    instead -- nothing acts in between, so it never takes hold.
    """
    ev = c.trigger
    if isinstance(ev, ForcedMove):
        ev.cancel(c.ref)
        return
    for effect in list(c.world.effects.of(c.me)):
        if Condition.PRONE in effect.conditions:
            c.world.effects.end(effect, c.ref)


@power(
    "p12705",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_BURNING_AT_DAWN,
    on=Trigger(DamageRolled, _burning_at_dawn, _BURNING_AT_DAWN),
)
def p12705(c: Cast) -> None:
    """The burn arrives empty and then gets a saving throw at +5, which is
    both halves of the printed line in the one window where the first is
    still possible."""
    ev = c.trigger
    if ev is None:
        return
    ev.amount = 0
    ev.cancel(c.ref)
    for effect in c.world.effects.of(c.me):
        if effect.when is When.SAVE_ENDS and effect.ongoing is not None:
            effect.save_mod += 5
            c.world.effects.save(effect)
            return


@power(
    "p12853",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_AM_HIT,
    on=Trigger(Hit, targets_me, _I_AM_HIT),
)
def p12853(c: Cast) -> None:
    c.shift(c.speed_of() + 4)


@power(
    "p13777",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.ARCANE],
    trigger=_ELEMENTAL_DAMAGE,
    on=Trigger(DamageRolled, _burned_me, _ELEMENTAL_DAMAGE),
)
def p13777(c: Cast) -> None:
    """"You and each ally in the burst" -- the ally pool already has the
    caster in it, so the header covers both. The type is the one that
    triggered this, read off the event."""
    kind = getattr(c.trigger, "dtype", None)
    if kind is not None and c.target is not None:
        c.resist(10, kind, on=c.target, until=When.EONT)


@power(
    "p2134",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    trigger=_RANGED_HIT_ME,
    on=Trigger(Hit, _ranged_hit_me, _RANGED_HIT_ME),
)
def p2134(c: Cast) -> None:
    c.surge(on=c.me, bonus=2 * c.wis_mod)
