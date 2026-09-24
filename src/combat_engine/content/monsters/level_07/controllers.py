"""Monster abilities, level 7: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=12)` and `Damage("2d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **blast whose target line reads "creatures in the blast"** is
`EACH_CREATURE`: a blast is thrown in front of its caster rather than
centred on it, so nothing has to be left out.

Six readings this file had to settle.

**Four rows print no range at all** -- the line is "+10 vs Will" and nothing
else. A weapon attack against AC is read as `Melee(1)`; an attack against a
mental defence is read at the reach the same creature's other ranged row
prints. Each one says so where it stands.

**"Recharge when it is first bloodied"** is a die in the header -- the spec
line prints one -- plus a `Bloodied` watch that hands the use straight back.
`Powers.restore` is the only thing that gives a spent row back, and the
watch is armed by the row itself, so a creature bloodied before it ever
fired gets nothing. That is what "first" means.

**A trait filed as a standard action** is still a trait -- `ActionType.NONE`,
so `Encounter.start` arms it rather than the creature spending its turn on
it.

**"The target cannot attack it"** and "it has no line of sight past 2
squares" are both a refusal in the interrupt window of `AttackDeclared`,
which is a `Decision` the emitter honours. Neither is a condition, and
approximating either with `blinded` would take away far more than the page
says.

**"Each Failed Saving Throw: ..."** is `Effect.escalate`, which runs on a
failed save -- as against `on_end`, which is what an Aftereffect wants.
Both shapes appear here and they are not the same clock.

**An aura's radius is a field on the zone**, so a row that expands one over
three turns moves `Zone.aura` and refreshes rather than tearing the aura
down and laying a wider one -- which would emit a full set of exits and
entries and fire every other row watching the aura.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Effect,
    Keyword,
    Melee,
    Mod,
    Moved,
    Powers,
    Ranged,
    Relation,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import spread
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    alive,
    allies,
    distance_between,
    has_combat_advantage,
    team,
)
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_keyword,
    by_melee,
    hits_me,
    targets_me,
)
from combat_engine.engine.zones import Zone

#: The five damage types m4815a4 answers.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _rearms_when_bloodied(c: Cast) -> None:
    """"Recharge when it is first bloodied", as a use handed back.

    Armed by the row, so a creature already bloodied when it first fires
    gets nothing -- the crossing has happened and `Bloodied` is emitted only
    on it.
    """
    known = c.world.get(c.me, Powers)
    ref, me = c.ref, c.me

    def again(ev: Bloodied) -> None:
        if ev.actor == me and known is not None:
            known.restore(ref)

    c.watch(Bloodied, again, until=When.ENCOUNTER, on=me, once=True, label=c.ref)


def _resist(c: Cast, dtype: DamageType, amount: int, *, until: When) -> None:
    """Shrug off `amount` of one damage type for a while.

    `Cast` has `vulnerable` and no opposite number, so this goes at
    `Defences.resist`, which is what `resolve.deal_damage` reads, with the
    effect carrying the undo.
    """
    shell = c.world.get(c.me, Defences) or c.world.add(c.me, Defences())
    had = shell.resist.get(dtype, 0)
    if amount <= had:
        return
    shell.resist[dtype] = amount

    def undo() -> None:
        if had:
            shell.resist[dtype] = had
        else:
            shell.resist.pop(dtype, None)

    c.world.effects.apply(c.me, c.me, until, label=f"{c.ref} resist", on_end=[undo])


def _vanish(c: Cast, until: When) -> None:
    """Unseen until it makes an attack roll.

    The roll gives it away whether or not it lands, so the watch is on
    `AttackRolled`, and it is torn down with the veil -- a second vanishing
    would otherwise inherit the first one's listener.
    """
    veil = c.invisible(until=until)
    if veil is None:
        return
    me = c.me

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=until, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


def _drags(c: Cast, victim: int):  # noqa: ANN202
    """"Each Failed Saving Throw: it slides the target 3 squares."

    `Effect.escalate` is what runs on a failed save. `on_end` is the other
    clock -- an Aftereffect -- and the two are a turn apart in practice.
    """

    def again(_eff: Effect) -> None:
        if alive(c.world, victim):
            c.slide(3, on=victim)

    return again


# --------------------------------------------------------------------------
# m281
# --------------------------------------------------------------------------


@power(
    "m281a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m281a0(c: Cast) -> None:
    """Ending a turn in it, which is neither of the two moments `c.hazard`
    bites at, so this is a `TurnEnd` watch. Who is inside is asked of the
    aura as the turn ends rather than tracked."""
    ring = c.aura(5, until=When.ENCOUNTER, label=c.ref)

    def press(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.damage("1d6", dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(TurnEnd, press, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m281a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m281a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m281a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.THUNDER),
)
def m281a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m281a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m281a3(c: Cast) -> None:
    """"3d6 + 4, or 3d6 + 9 if it is bloodied" is two expressions, so the
    damage is rolled in the body; the header keeps the base line, which is
    what the card and the policy read.

    The spec line prints a recharge die and the printed sentence says it
    comes back when the m281 is first bloodied. Both are honoured: the die
    in the header, the crossing as a watch that hands the use back.
    """
    if c.first:
        _rearms_when_bloodied(c)
    bonus = 9 if c.bloodied(on=c.me) else 4
    if c.strike():
        c.damage("3d6", bonus, dtype=DamageType.THUNDER)
    else:
        c.half_damage("3d6", bonus, dtype=DamageType.THUNDER)


@power(
    "m281a4",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m281a4(c: Cast) -> None:
    c.teleport(10)


@power(
    "m281a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m281a5(c: Cast) -> None:
    """A disguise and nothing else: the shape carries no statistics, gates
    no other row and lasts as long as it is wanted. Deliberately inert."""
    c.note("m281a5: takes the shape of any Medium humanoid")


# --------------------------------------------------------------------------
# m2813
# --------------------------------------------------------------------------

#: The two shapes m2813a4 chooses between, and the prefix its hold is
#: labelled with so the three attacks can read which one is in force.
_M2813_SHAPES = ("wolf", "hobgoblin")
_M2813_SHAPE = "m2813a4 "


def _m2813_in(word: str):  # noqa: ANN202
    """A printed "usable only in <x> form", asked of the creature.

    A m2813 that has not changed shape yet is in whatever shape it was found
    in, which the stat block does not say -- so an undeclared form rules out
    neither attack. Once it has changed, the hold is the answer.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(_M2813_SHAPE):
                return effect.label.endswith(word)
        return True

    return gate


@power(
    "m2813a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
    requires=_m2813_in("wolf"),
    requires_text="the m2813 must be in its wolf form",
)
def m2813a0(c: Cast) -> None:
    """No range printed. A bite against AC is `Melee(1)`."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2813a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
    requires=_m2813_in("hobgoblin"),
    requires_text="the m2813 must be in its hobgoblin form",
)
def m2813a1(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`.

    Invisible **to the target** and to nobody else, which is what `to=`
    narrows -- an unseen creature is held as one relation per watcher.
    """
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.invisible(to=victim, until=When.EONT)


@power(
    "m2813a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m2813a2(c: Cast) -> None:
    """The Aftereffect hangs on `on_end` rather than on `escalate`:
    escalation runs on a *failed* save, and an aftereffect is what happens
    when the first effect finally ends. The daze is on a clock rather than a
    save, so there is no failed save for it to run on at all."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hold = c.dazed(until=When.EONT)
    if hold is None or victim is None:
        return

    def afterwards() -> None:
        if alive(c.world, victim):
            c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)

    hold.on_end.append(afterwards)


@power(
    "m2813a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 1, dtype=DamageType.NECROTIC, kind=LIMITED),
    requires=_m2813_in("wolf"),
    requires_text="the m2813 must be in its wolf form",
)
def m2813a3(c: Cast) -> None:
    """The mending is keyed off the burning's own event: ongoing damage is
    dealt with `detail=str(effect)`, so the blow this row profits from is
    the one whose detail is this effect and no other. Reading the damage
    type alone would pay out for anybody else's necrotic too."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    burn = c.ongoing(5, DamageType.NECROTIC)
    if burn is None or victim is None:
        return
    me, mark = c.me, str(burn)

    def mend(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0 and ev.detail == mark:
            c.heal(5, on=me)

    burn.subs.append(c.world.bus.on(DamageApplied, mend, owner=me))


@power(
    "m2813a4",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    once_per_round=True,
)
def m2813a4(c: Cast) -> None:
    """Two shapes and nothing else: the statistics do not change, so all the
    form is for is the Requirement on the three attacks above.

    Using it again ends the shape it was in, which `c.form` does not do for
    itself -- a polymorph is not a stance, and this one is printed as one.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(_M2813_SHAPE):
            c.world.effects.end(effect, "it changed shape again")
    shape = c.choose(list(_M2813_SHAPES), "which shape") or _M2813_SHAPES[0]
    c.form(until=When.ENCOUNTER, revert=None, label=f"{_M2813_SHAPE}{shape}")


_M2813_STRUCK = "the m2813 is hit by a melee attack"


@power(
    "m2813a5",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2813_STRUCK,
    on=Trigger(Hit, when=both(hits_me, by_melee), text=_M2813_STRUCK),
)
def m2813a5(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m2993
# --------------------------------------------------------------------------


@power(
    "m2993a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 4),
)
def m2993a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`."""
    if c.strike():
        c.hit()


@power(
    "m2993a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
)
def m2993a1(c: Cast) -> None:
    """No range printed. A charm against Will is read at the reach the
    m2993's other ranged charm prints, which is 10.

    No damage at all -- the whole of the hit is the swing it borrows, and
    `c.grant_attack` rolls whatever that creature's own basic attack is,
    which is the printed "basic attack".
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    near = sorted(
        a
        for a in allies(c.world, victim)
        if a != victim and alive(c.world, a) and adjacent(c.world, victim, a)
    )
    friend = c.choose(near, "which of its allies it turns on") if near else None
    if friend is not None:
        c.grant_attack(victim, on=friend)


@power(
    "m2993a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m2993a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m2993a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m2993a3(c: Cast) -> None:
    """"Cannot attack the m2993" is a refusal in the interrupt window of
    `AttackDeclared`, which is a `Decision` its emitter honours. It is not a
    condition: nothing in the table means "may not attack one named
    creature", and dazing or stunning would take away far more.

    Both halves hang on one hold, so the saving throw the second half offers
    is a throw against the thing the first half is doing. `Effects.save` is
    given the effect by name rather than `c.save`, which takes the first
    save-ends effect it finds on the creature.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    hold = c.effect(c.ref, until=When.SAVE_ENDS)
    if hold is None:
        return
    me = c.me

    def veto(ev: AttackDeclared) -> None:
        if not hold.ended and ev.attacker == victim and ev.target == me:
            ev.cancel("it cannot bring itself to")

    def reprieve(ev: AttackRolled) -> None:
        if not hold.ended and ev.attacker == me and ev.target == victim:
            c.world.effects.save(hold)

    hold.subs.append(
        c.world.bus.on(AttackDeclared, veto, window=Window.BEFORE, owner=me)
    )
    hold.subs.append(c.world.bus.on(AttackRolled, reprieve, owner=me))


@power(
    "m2993a4",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2993a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Combat advantage is asked of the board at the moment of the hit:
    flanking ends the instant an ally steps away, and a stored flag would
    not notice.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and has_combat_advantage(c.world, me, ev.target):
            c.damage("2d6", on=ev.target, detail=c.ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m2993a5",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2993a5(c: Cast) -> None:
    """The Stealth half is narrative -- the engine has no skill checks and
    no penalty for moving to waive -- so the row is the shift."""
    c.shift(6)


# --------------------------------------------------------------------------
# m3007
# --------------------------------------------------------------------------

#: The label the hex leaves behind. Three other rows read it.
_M3007_HEX = "m3007a2"


def _hexed_by(world: World, eid: int, by: int) -> bool:
    return any(
        eff.label == _M3007_HEX and eff.source == by and not eff.ended
        for eff in world.effects.of(eid)
    )


def _has_a_hexed_enemy(world: World, eid: int) -> bool:
    """A printed "targets a hexed enemy", asked of the board.

    `requires` is handed the caster and no target, so the nearest thing it
    can say is that there is somebody carrying the hex. Which one is then
    the chooser's business, and the body asks again per target.
    """
    from combat_engine.engine.query import enemies

    return any(_hexed_by(world, foe, eid) for foe in enemies(world, eid))


@power(
    "m3007a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 1),
)
def m3007a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`."""
    if c.strike():
        c.hit()


@power(
    "m3007a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POLYMORPH, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    requires=_has_a_hexed_enemy,
    requires_text="one of the m3007's enemies must be hexed",
)
def m3007a1(c: Cast) -> None:
    """"Cannot use powers" is every row taken away and given back together.
    `c.forbid` leaves the row in the creature's list and out of reach, which
    is what "cannot use" is as against spending it.

    Becoming Tiny is the flavour of the same sentence: nothing in the engine
    reads a creature's size for anything the printed line cares about, and
    the whole mechanical content is the bar on its powers.
    """
    victim = c.target
    if victim is None or not _hexed_by(c.world, victim, c.me):
        return
    if not c.strike():
        return
    known = c.world.get(victim, Powers)
    for ref in list(known.all) if known else []:
        c.forbid(ref, on=victim, until=When.EONT)


@power(
    "m3007a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m3007a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hex.

    Both penalties ride on **one** effect, so the victim gets one saving
    throw and not two, and the gate is on the damage and attack contexts'
    `target` key -- which both of them carry.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    me = c.ref, c.me
    owner = me[1]

    def against_the_hexer(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == owner

    c.world.effects.apply(
        victim,
        owner,
        When.SAVE_ENDS,
        label=_M3007_HEX,
        mods=[
            (victim, Mod(what=what, value=-2, kind="untyped",
                         when=against_the_hexer, label=_M3007_HEX))
            for what in ("attack", "damage")
        ],
    )


@power(
    "m3007a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d10", 3, kind=LIMITED),
    requires=_has_a_hexed_enemy,
    requires_text="one of the m3007's enemies must be hexed",
)
def m3007a3(c: Cast) -> None:
    """The printed target line is "hexed creatures", which `Target` cannot
    carry -- it holds a side and a count and no condition -- so an unhexed
    creature in the burst is simply not attacked."""
    victim = c.target
    if victim is None or not _hexed_by(c.world, victim, c.me):
        return
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


@power(
    "m3007a4",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3007a4(c: Cast) -> None:
    """"Either ... or" is a choice the caster makes, so `c.may` is asked of
    the caster -- it asks `c.target` by default, and this row has none."""
    near = sorted(
        x
        for x in c.suffering(_M3007_HEX)
        if alive(c.world, x) and c.distance(to=x) <= 5
    )
    if near and c.may("swap places with a hexed creature", who=c.me):
        friend = c.choose(near, "which hexed creature") or near[0]
        c.swap(friend)
        return
    c.teleport(5)


# --------------------------------------------------------------------------
# m406
# --------------------------------------------------------------------------


@power(
    "m406a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m406a0(c: Cast) -> None:
    """No range printed; read at the reach the m406's other ranged row
    prints, which is 10.

    "Fire and necrotic damage" is one blow of two types and `Damage` carries
    one. Necrotic is the one written, both are declared as keywords, and a
    creature resistant to fire alone will therefore take it in full where
    the printed rule would let the resistance apply.
    """
    if c.strike():
        c.hit()


@power(
    "m406a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m406a1(c: Cast) -> None:
    """"No line of sight to anything more than 2 squares away" is a refusal
    in the interrupt window of `AttackDeclared`: the victim may still swing
    at what it is standing next to and at nothing further off.

    Not `c.blinded`, which takes away the two squares as well and hands
    everyone on the board combat advantage the printed line never grants.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    hold = c.effect(c.ref, until=When.SAVE_ENDS)
    if hold is None:
        return

    def veto(ev: AttackDeclared) -> None:
        if hold.ended or ev.attacker != victim:
            return
        if distance_between(c.world, victim, ev.target) > 2:
            ev.cancel("it cannot see that far")

    hold.subs.append(
        c.world.bus.on(AttackDeclared, veto, window=Window.BEFORE, owner=c.me)
    )


@power(
    "m406a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
)
def m406a2(c: Cast) -> None:
    """The shadows are an aura rather than a zone -- they follow her -- and
    everything the printed line says hangs on that one aura's effect, which
    is the thing carrying the Sustain Minor cost.

    **Difficult terrain** is a field on the zone; `Zones.difficult_squares`
    reads every zone including an aura, and only `c.zone` takes the
    argument. "Including flying ones" is free: the engine charges everybody
    for rough ground.

    **Concealment** is the -2 that concealment is, gated on the *target*
    being in the aura -- so it moves as the aura moves and as people walk in
    and out of it. It sits on each enemy, because a modifier to an attack
    roll is read off the attacker. `blocks_sight` is the near neighbour and
    the wrong one here: `cover_between` deliberately excludes the squares
    either party is standing in, so a zone of darkness shelters what is
    behind it and never what is inside it.

    **The bite is enemies only**, which `c.burns` does not ask, so both of
    its watches are written out.

    The printed line also ends the aura if she uses a row this stat block
    does not have -- the id names another creature's ability -- so that half
    can never fire and is left out. Moving more than half her speed is the
    half that can.
    """
    me = c.me
    ring = c.aura(2, until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    shadows = c.world.get(ring, Zone)
    if shadows is None or shadows.effect is None:
        return
    shadows.difficult = True
    hold = shadows.effect
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == me or who not in c.enemies() or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(5, dtype=DamageType.NECROTIC, on=who)

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def on_start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    def concealed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or who not in c.world.zones.occupants(ring):
            return False
        return who == me or c.is_kind("shadow", on=who)

    walked = {"steps": 0}

    def stepped(ev: Moved) -> None:
        if ev.actor != me or c.world.turn != me:
            return
        walked["steps"] += 1
        if walked["steps"] > c.speed_of(me) // 2:
            c.world.effects.end(hold, "it walked out of its own shadows")

    def fresh(ev: TurnStart) -> None:
        if ev.actor == me:
            walked["steps"] = 0

    hold.subs.append(c.world.bus.on(ZoneEntered, on_enter, owner=me))
    hold.subs.append(c.world.bus.on(TurnStart, on_start, owner=me))
    hold.subs.append(c.world.bus.on(Moved, stepped, owner=me))
    hold.subs.append(c.world.bus.on(TurnStart, fresh, owner=me))
    for foe in c.enemies():
        veil = c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=concealed)
        if veil is not None:
            hold.on_end.append(
                lambda v=veil: c.world.effects.end(v, "the shadows lifted")
            )


@power(
    "m406a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m406a3(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


# --------------------------------------------------------------------------
# m4815
# --------------------------------------------------------------------------


@power(
    "m4815a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4815a0(c: Cast) -> None:
    """A penalty to saving throws cannot be a gated modifier: `Effects.save`
    reads `Mods.total("save")` with no context at all, so a `when=` on it is
    never consulted. Membership is therefore tracked -- the penalty goes on
    as a creature walks in and comes off as it walks out.

    Whoever is already standing in it when it goes up is handled by hand:
    `Zones.create` refreshes as it spawns, so those entries were announced
    before there was an id to watch for.
    """
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)
    held: dict[int, Effect] = {}

    def clamp(who: int) -> None:
        if who == me or who not in c.enemies():
            return
        if who in held and not held[who].ended:
            return
        marked = c.penalty("save", 2, on=who, until=When.ENCOUNTER)
        if marked is not None:
            held[who] = marked

    def steps_in(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            clamp(ev.actor)

    def steps_out(ev: ZoneExited) -> None:
        if ev.zone != ring:
            return
        gone = held.pop(ev.actor, None)
        if gone is not None:
            c.world.effects.end(gone, "left the aura")

    c.watch(ZoneEntered, steps_in, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(ZoneExited, steps_out, until=When.ENCOUNTER, on=me, label=c.ref)
    for who in c.world.zones.occupants(ring):
        clamp(who)


@power(
    "m4815a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m4815a1(c: Cast) -> None:
    """Melee 0 as printed: a Tiny creature reaches only into its own square,
    so this lands on whatever it is sharing one with. `c.shift(share=True)`
    is how anything gets there, and nothing on a bare board ever is -- the
    row is correct and unreachable until something melds."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS, to="allies")


@power(
    "m4815a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
    once_per_round=True,
)
def m4815a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the daze, and the second
    way out of it rides on the same effect, so striking at its own ends the
    thing rather than shortening it."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    hold = c.dazed(until=When.SAVE_ENDS)
    if hold is None:
        return

    def turncoat(ev: AttackDeclared) -> None:
        if hold.ended or ev.attacker != victim:
            return
        if ev.target in allies(c.world, victim):
            c.world.effects.end(hold, "it struck at its own")

    hold.subs.append(c.world.bus.on(AttackDeclared, turncoat, owner=c.me))


@power(
    "m4815a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    once_per_round=True,
)
def m4815a3(c: Cast) -> None:
    """"Until it makes an attack roll" is a clock nothing measures, so the
    veil is held to the end of the encounter and spent by the roll."""
    _vanish(c, When.ENCOUNTER)


_M4815_SEARED = "the m4815 takes acid, cold, fire, lightning or thunder damage"


def _elemental_hit(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _ELEMENTS
    )


@power(
    "m4815a4",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4815_SEARED,
    on=Trigger(DamageApplied, when=_elemental_hit, text=_M4815_SEARED),
)
def m4815a4(c: Cast) -> None:
    """`DamageApplied` rather than `Hit`: the printed trigger is taking the
    damage, so a blow something else ate whole is not one, and the type is
    on the damage event and on nothing else."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype in _ELEMENTS:
        _resist(c, dtype, 10, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4839
# --------------------------------------------------------------------------


@power(
    "m4839a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m4839a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4839a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d10", 2, dtype=DamageType.FIRE),
)
def m4839a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m4839a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
)
def m4839a2(c: Cast) -> None:
    """"Choose one creature within 2 squares" is any creature, not an enemy,
    so the row declares no target and picks from the board: `Target` carries
    a side and this line names none.

    The drag comes first, as printed, so the swing is taken from wherever it
    leaves the creature standing -- and whom it can reach is asked after.
    """
    near = sorted(x for x in c.within(2) if x != c.me and alive(c.world, x))
    who = c.choose(near, "who it drags") if near else None
    if who is None:
        return
    c.slide(3, on=who)
    reachable = sorted(
        f
        for f in c.within(1, of=who)
        if f != who and alive(c.world, f)
    )
    foe = c.choose(reachable, "who it is made to strike") if reachable else None
    if foe is not None:
        c.grant_attack(who, on=foe)


def _with_a_melee_row(ctx: dict[str, Any]) -> bool:
    """Was the blow a melee attack? The damage context carries the ref."""
    p = get(ctx.get("power") or "")
    return p is not None and p.reach.kind == "melee"


@power(
    "m4839a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.FIRE],
)
def m4839a3(c: Cast) -> None:
    """"Until the end of the ally's next turn" is the *target's* clock,
    which is `EOTNT`.

    The extra damage is untyped: a modifier carries a number and no damage
    type, so a target resistant to fire takes this where the printed line
    would let the resistance eat it.
    """
    c.bonus("damage", 5, until=When.EOTNT, when=_with_a_melee_row)


_M4839_ALLY_MISSED = "an ally within 10 squares of the m4839 misses with an attack"


def _ally_missed(world: World, me: int, ev: Any) -> bool:
    """The triggering ally is the one that *swung*.

    `ally_within` reads `ev.actor` and falls back to `ev.target`, and `Miss`
    has no actor -- so it would have measured to the creature that was
    missed rather than to the one that missed it.
    """
    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "m4839a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4839_ALLY_MISSED,
    on=Trigger(Miss, when=_ally_missed, text=_M4839_ALLY_MISSED),
)
def m4839a4(c: Cast) -> None:
    """An interrupt on the miss, which is where the roll can still be
    changed: `resolve.attack` re-reads the result after this window and
    turns the `Miss` into a `Hit` if the new number lands.

    `c.reroll_attack` takes no bonus, so the printed +2 is added to the
    total afterwards and the outcome recomputed from it -- the same two
    lines `resolve` runs once the window closes.

    The other half of the printed trigger is a failed skill check, which the
    engine has no event for and so cannot answer.
    """
    result = getattr(c.trigger, "result", None)
    if not c.reroll_attack() or result is None:
        return
    result.total += 2
    result.hit = result.critical or (
        result.natural != 1 and result.total >= result.target_defence
    )


# --------------------------------------------------------------------------
# m4841
# --------------------------------------------------------------------------

#: The aura m4841a0 lays down. Two other rows move it and read it; the
#: printed lines name it by an id belonging to a smaller cousin's stat
#: block, and this is the aura they mean.
_M4841_AURA = "m4841a0"


def _m4841_ring(world: World, eid: int) -> tuple[int, Zone] | None:
    for zid, zone in world.zones.all():
        if zone.label == _M4841_AURA and zone.owner == eid:
            return zid, zone
    return None


def _ring_at_one(world: World, eid: int) -> bool:
    """The printed recharge condition: the aura must be back at its own
    size. Nothing rolls a die for this row -- recharge 1 always comes back
    -- so the condition is what actually decides when it is available."""
    found = _m4841_ring(world, eid)
    return found is not None and found[1].aura == 1


@power(
    "m4841a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4841a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def shove(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slide(1, on=ev.actor)

    c.watch(TurnEnd, shove, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m4841a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.COLD),
)
def m4841a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4841a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8, dtype=DamageType.COLD),
)
def m4841a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m4841a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4841a3(c: Cast) -> None:
    """Two swings of the rows that print them, aimed one at a time: the
    second is chosen after the first has resolved, which is the printed
    order and matters when the first one kills."""
    pair = c.choose(["one of each", "the second one twice"], "which pair")
    refs = ["m4841a2", "m4841a2"] if pair == "the second one twice" else [
        "m4841a1",
        "m4841a2",
    ]
    for ref in refs:
        reachable = sorted(f for f in c.within(2, side="enemy") if alive(c.world, f))
        foe = c.choose(reachable, "who the claws find") if reachable else None
        if foe is None:
            return
        use(c.world, c.me, ref, targets=[foe], spend=False)


@power(
    "m4841a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=1,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 5, dtype=DamageType.COLD, kind=LIMITED),
    requires=_ring_at_one,
    requires_text="the m4841's aura must be at its own size",
)
def m4841a4(c: Cast) -> None:
    """Three turns in one row: the aura widens, widens again, and then
    breaks. The attack is two turns off, so the row declares no targets and
    no reach -- `c.strike(on=...)` still rolls the line the header holds,
    which is what keeps the numbers data.

    The radius is a field on the zone, moved and refreshed rather than torn
    down and relaid: relaying it would announce a full set of exits and
    entries and fire every row watching the aura twice.
    """
    found = _m4841_ring(c.world, c.me)
    if found is None:
        return
    _, ring = found
    ring.aura = 3
    c.world.zones.refresh()
    me = c.me
    stage = {"n": 0}

    def tick(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        stage["n"] += 1
        if stage["n"] == 1:
            ring.aura = 5
            c.world.zones.refresh()
            return
        for foe in sorted(c.within(5, side="enemy")):
            if c.strike(on=foe):
                c.hit(on=foe)
                c.condition(
                    Condition.SLOWED,
                    Condition.BLINDED,
                    until=When.SAVE_ENDS,
                    on=foe,
                )
        ring.aura = 1
        c.world.zones.refresh()
        c.world.effects.end(clock, "the breath is spent")

    clock = c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=c.ref)


_M4841_HURT = "an enemy's melee attack deals damage to the m4841"


def _hurt_in_melee(world: World, me: int, ev: Any) -> bool:
    source = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and source is not None
        and team(world, source) is not team(world, me)
        and by_melee(world, me, ev)
    )


@power(
    "m4841a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d10", 5, dtype=DamageType.COLD, kind=LIMITED),
    trigger=_M4841_HURT,
    on=Trigger(DamageApplied, when=_hurt_in_melee, text=_M4841_HURT),
)
def m4841a5(c: Cast) -> None:
    """`DamageApplied` rather than `Hit`: the printed trigger is the damage
    landing, so a blow a resistance ate whole is not one. `by_melee` reads
    the reach off the row named in the event's `detail`.

    The spec line prints a recharge die and the printed sentence says it
    comes back when the m4841 is first bloodied; both are honoured.
    """
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


_M4841_CHILLED = "the m4841 is hit by a cold attack"


@power(
    "m4841a6",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4841_CHILLED,
    on=Trigger(
        Hit, when=both(targets_me, by_keyword(Keyword.COLD)), text=_M4841_CHILLED
    ),
)
def m4841a6(c: Cast) -> None:
    """`targets_me`, not `about_me`: an attack event names its subject
    `target`, and `about_me` reads `ev.actor` and only that."""
    found = _m4841_ring(c.world, c.me)
    if found is None:
        return
    for foe in c.world.zones.occupants(found[0]):
        if foe != c.me and foe in c.enemies():
            c.slide(1, on=foe)


# --------------------------------------------------------------------------
# m4903
# --------------------------------------------------------------------------

#: What the m4903 calls up. The printed lines name the spirit by two
#: different ids -- one of them this row's own -- and both are this.
_M4903_SPIRIT = "m234"


def _spirits_of(world: World, eid: int, within: int) -> list[int]:
    """Its own spirits, in range. Held as `MASTER_OF`, which `c.bind` sets
    and `c.servants` reads -- nothing else says "one of *its* spirits"."""
    return sorted(
        s
        for s in world.relations.targets(Relation.MASTER_OF, eid)
        if alive(world, s) and distance_between(world, eid, s) <= within
    )


def _has_a_spirit(world: World, eid: int) -> bool:
    return bool(_spirits_of(world, eid, 10))


def _call_up(c: Cast, how_many: int) -> None:
    """Spirits, bound to their caller, and the toll for losing one.

    `c.summon` is both halves: `loader.spawn` alone leaves a creature
    standing outside the initiative order, never acting. The printed line
    says only "within 10 squares" and names no square, so they arrive in the
    free squares nearest the m4903.
    """
    me = c.me
    made = {s for _ in range(how_many) if (s := c.summon(_M4903_SPIRIT))}
    for spirit in sorted(made):
        c.bind(on=spirit)

    def toll(ev: Dropped) -> None:
        if ev.actor in made:
            c.flat(5, on=me)

    if made:
        c.watch(Dropped, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4903a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4903a0(c: Cast) -> None:
    """"Melee attacks" is the reach kind and not `by_melee`, which also
    counts a close burst -- the printed word is the narrower one.

    Who is crowding the victim is asked at the moment of the hit: the ring
    round a creature changes every time anybody steps.
    """
    me = c.me

    def mobbed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is None or p.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        pack = [
            a
            for a in allies(c.world, me)
            if a != me
            and c.is_kind("gnoll", on=a)
            and adjacent(c.world, a, ev.target)
        ]
        if len(pack) >= 2:
            c.flat(5, on=ev.target)

    c.watch(Hit, mobbed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4903a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m4903a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4903a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.TELEPORTATION,
        Keyword.RANGED,
    ],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m4903a2(c: Cast) -> None:
    """The spirit's arrival is named outright -- "a square adjacent to the
    target" -- so the destination is chosen from the free squares beside the
    victim rather than left to the decider, which would take the lowest
    square within ten and call it a teleport."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    near = _spirits_of(c.world, c.me, 10)
    if not near:
        return
    spirit = c.choose(near, "which spirit steps in") or near[0]
    beside = squares_of(c.world, victim)
    free = sorted(
        sq
        for sq in spread(beside, 1) - beside
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) in (None, spirit)
    )
    if free:
        c.teleport(20, who=spirit, to=free[0])


@power(
    "m4903a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4903a3(c: Cast) -> None:
    _call_up(c, 4)


@power(
    "m4903a4",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m4903a4(c: Cast) -> None:
    _call_up(c, 1)


@power(
    "m4903a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    requires=_has_a_spirit,
    requires_text="the m4903 must have a spirit within 10 squares",
)
def m4903a5(c: Cast) -> None:
    """The swing is the spirit's own row, named rather than left to its
    basic attack, because the printed line says which one."""
    near = _spirits_of(c.world, c.me, 10)
    if not near:
        return
    spirit = c.choose(near, "which spirit bites") or near[0]
    reachable = sorted(
        f
        for f in c.enemies()
        if alive(c.world, f) and adjacent(c.world, spirit, f)
    )
    foe = c.choose(reachable, "who it bites") if reachable else None
    if foe is not None:
        c.grant_attack(spirit, on=foe, ref="m234a2", attack_bonus=2)


@power(
    "m4903a6",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    once_per_round=True,
)
def m4903a6(c: Cast) -> None:
    for friend in sorted(c.within(1, side="ally")):
        if friend != c.me:
            c.teleport(10, who=friend)


# --------------------------------------------------------------------------
# m4997
# --------------------------------------------------------------------------


@power(
    "m4997a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 7),
)
def m4997a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    burn = c.ongoing(5, DamageType.POISON)
    if burn is not None and victim is not None:
        burn.escalate = _drags(c, victim)


@power(
    "m4997a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
)
def m4997a1(c: Cast) -> None:
    """No damage on the hit at all -- the whole of it is the burning."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    burn = c.ongoing(10, DamageType.POISON)
    if burn is not None:
        burn.escalate = _drags(c, victim)


_M4997_STRUCK = "an enemy hits the m4997 with a melee attack"


@power(
    "m4997a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M4997_STRUCK,
    on=Trigger(Hit, when=both(hits_me, by_melee), text=_M4997_STRUCK),
)
def m4997a2(c: Cast) -> None:
    c.teleport(3)
