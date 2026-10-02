"""Wizard, level 5: the daily attacks.

Three of the four leave something on the board -- a conjuration and two
zones -- and all three of those are built from `c.area()`, which reads the
aim point off the `Cast`. The caveat in `level_1.py` still holds: a caller
that lets the engine pick the aim gets a burst centred near the caster.

`c.hazard` cannot say "blocks line of sight", so the obscuring zone is made
with `c.zone(..., blocks_sight=True)` and given its teeth separately with
`c.burns` -- the two halves `c.hazard` is.

The rows printed in the later books follow. Three things recur in them:

* **Teeth that are not `c.burns`.** That method is "enters, or starts its
  turn there, once per turn". A row printing "enters or **ends** its turn
  there", or one biting enemies only, writes the latch out and hangs the
  listeners on the zone's own effect.
* **A secondary attack on a different line.** `c.strike` rolls the header's
  one attack, so a secondary against another defence goes through
  `c.attack(c.int_, <defence>)`.
* **The four summoning rows of this level.** Three are written on
  `Summon` in the header and `c.summon_inline` in the body; each prints a
  command spent on a later standard action, and nothing offers one, so
  the header declares the line and the body cannot spend it. The fourth
  is absent -- see the report.

`p10071`'s printed Requirement is a staff, and the wizard build carries no
weapon at all, so the row is refused on this board for a reason that says
nothing about the row.
"""

from __future__ import annotations

from combat_engine.content.powers.wizard.level_1_d import (
    _at_will_or_basic,
    _commands_on_opportunity,
    _reach_is,
)
from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    INT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    Condition,
    ConditionApplied,
    Damage,
    DamageApplied,
    DamageType,
    Gear,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Relation,
    Summon,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    World,
    enemy_within,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import OpportunityWindow, RelationSet, ZoneEntered
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _staff(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    main = gear.main if gear else None
    return bool(main and ("staff" in main.properties or main.group == "staff"))


@power(
    "p1195",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    # "One creature adjacent to the hand" -- the hand is placed next to
    # whoever was picked, which is the same thing said from the other end.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p1195(c: Cast) -> None:
    """The hand occupies a square, swings with its maker's numbers from its
    own position, and is walked six squares with a move action -- all of
    which `c.conjure` is.

    The grab is the caster's rather than the hand's. A conjuration holds no
    relations of its own, and the printed escape line already rolls against
    the caster's defences, so this is where the clause was pointing anyway.

    Two clauses have no vocabulary and are left off rather than guessed at:
    that commanding it again is barred while it has hold of somebody, and
    that the caster may let go as a free action.
    """
    if not c.first:
        return
    victim = c.target
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    hand = c.conjure(
        c.choose(room, "where the hand stands"),
        label="p1195",
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=6,
    )
    if not hand:
        return
    # It appears swinging.
    if victim is not None and c.strike(from_=hand):
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.grab()

    def squeeze() -> None:
        for caught in c.world.relations.targets(Relation.GRABBED_BY, c.me):
            c.damage("1d8", c.int_mod, dtype=DamageType.COLD, on=caught)

    conj = c.world.get(hand, Conjuration)
    c.on_sustain(c.world.effects.live.get(conj.effect) if conj else None, squeeze)


@power(
    "p1553",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p1553(c: Cast) -> None:
    if c.strike():
        c.damage("4d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("4d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p259",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p259(c: Cast) -> None:
    """No damage anywhere on the row: the hit line is the condition, and the
    ground it leaves behind keeps applying the same one.

    A creature already held is not held twice -- stacking a second save-ends
    copy on every step it finishes in the mud would need two saves to undo
    one effect, and the printed line reads as one condition, reapplied.
    """
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    c.zone(area, label="p259", until=When.ENCOUNTER, difficult=True)

    def caught(ev: MoveEnd) -> None:
        if ev.actor in c.in_squares(area) and not c.is_(Condition.IMMOBILIZED, on=ev.actor):
            c.immobilized(until=When.SAVE_ENDS, on=ev.actor)

    c.watch(MoveEnd, caught, until=When.ENCOUNTER, label="p259")


@power(
    "p67",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p67(c: Cast) -> None:
    """"Heavily obscured" is line of sight, which is a zone's business and
    not a hazard's, so the cloud and its teeth are built in two steps.

    Walking the zone six squares with a move action has no expression -- a
    zone's squares are fixed where they were laid -- so the cloud stands.
    """
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.POISON)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    cloud = c.zone(area, label="p67", until=When.EONT, blocks_sight=True)
    c.burns(cloud, 5 + c.int_mod, DamageType.POISON)


@power(
    "p10071",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
    requires=_staff,
    requires_text="needs a staff in hand",
    trigger="an enemy moves to within 2 squares of you",
    on=Trigger(
        MoveEnd,
        when=enemy_within(2),
        text="an enemy moves to within 2 squares of you",
    ),
)
def p10071(c: Cast) -> None:
    """The shove is an Effect line and happens either way. The trigger is read
    off the finished move rather than the start of it: `MoveStart` fires before
    a step has been taken, so nothing is within two squares yet."""
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED, Condition.DAZED, until=When.EONT)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED, until=When.EONT)
    c.push(5)


@power(
    "p11034",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p11034(c: Cast) -> None:
    """The primary rolls Fortitude and the secondary Reflex, so only one of
    them can be the header's line; the secondary is the one that deals the
    damage and a policy should be able to read it, so it is the header's and
    the sliding half goes through `c.attack`.

    The secondary waits until the burst has finished shoving everybody about,
    which is the printed order.
    """
    if c.attack(c.int_, FORT):
        c.slide(2)
    if not c.last:
        return
    foes = sorted(x for x in c.targets if x in c.enemies())
    mark = c.choose(foes, f"{c.ref}: where the bolt lands") if foes else None
    if mark is None:
        return
    for who in sorted(c.within(1, of=mark)):
        if c.strike(on=who):
            c.damage("2d8", c.int_mod, dtype=DamageType.LIGHTNING, on=who)
        else:
            c.half_damage("2d8", c.int_mod, dtype=DamageType.LIGHTNING, on=who)


@power(
    "p12744",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p12744(c: Cast) -> None:
    """"This effect also ends if the target is attacked" is a watch hung on the
    hold itself, so one thing ends both. The Aftereffect follows the hold going,
    whichever way it went -- which is what `on_end` is, and is why a target
    shaken awake early still swings.
    """
    victim = c.target
    if victim is None:
        return
    landed = c.strike()
    held = c.stunned(until=When.SONT) if landed else c.dazed(until=When.EONT)
    if held is None:
        return

    if landed:

        def afterwards() -> None:
            foes = sorted(x for x in c.enemies() if x != victim)
            mark = c.choose(foes, f"{c.ref}: who the target swings at") if foes else None
            if mark is not None:
                c.grant_attack(victim, on=mark)

        held.on_end.append(afterwards)

    def struck(ev: AttackDeclared) -> None:
        if ev.target == victim and not held.ended:
            c.world.effects.end(held, "the target was attacked")

    held.subs.append(c.world.bus.on(AttackDeclared, struck, owner=c.me))


@power(
    "p14551",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POLYMORPH],
    attack=Attack(INT, vs=FORT),
)
def p14551(c: Cast) -> None:
    """A shape is `Condition.SHAPED` -- no standard action, so the only things
    left are moving and shifting -- alongside the daze the row prints. Being
    Tiny and the equipment coming with it are fiction the board has no use for.
    Any damage at all ends it, which is a watch hung on the same hold.
    """
    victim = c.target
    if victim is None:
        return
    until = When.SAVE_ENDS if c.strike() else When.EOTNT
    held = c.condition(Condition.DAZED, Condition.SHAPED, until=until)
    if held is None:
        return

    def hurt(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0 and not held.ended:
            c.world.effects.end(held, "the shape was broken")

    held.subs.append(c.world.bus.on(DamageApplied, hurt, owner=c.me))


@power(
    "p14552",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POLYMORPH],
    attack=Attack(INT, vs=FORT),
)
def p14552(c: Cast) -> None:
    """"Must make an opportunity attack" is the engine making the swing: the
    window is opened by whoever walks off and nothing in the engine ever
    decides what goes in one, so the compulsion is a listener that grants the
    attack when the window opens against this creature.
    """
    victim = c.target
    if victim is None:
        return
    landed = c.strike()
    if landed:
        c.damage("2d8", c.int_mod)
    else:
        c.half_damage("2d8", c.int_mod)
    held = c.effect(
        f"{c.ref} savagery", until=When.SAVE_ENDS if landed else When.EONT
    )
    if held is None:
        return

    def lash(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            c.grant_attack(victim, on=ev.provoker)

    held.subs.append(c.world.bus.on(OpportunityWindow, lash, owner=c.me))
    if not landed:
        return

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == victim:
            return
        if c.adjacent_to(victim, ev.actor):
            c.flat(5 + c.int_mod, on=ev.actor)

    held.subs.append(c.world.bus.on(TurnEnd, dusk, owner=c.me))


@power(
    "p16280",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("any", 1, label="You or one ally"),
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p16280(c: Cast) -> None:
    """The aura follows whoever it was hung on, which is what `c.aura(on=)` is
    for. Its bite is entering or **ending** a turn there, which is not the
    sentence `c.burns` carries, so the once-per-turn latch is written out.

    "Until the target dismisses it as a minor action" and the partial
    concealment are the two clauses with nowhere to go.
    """
    who = c.target
    if who is None:
        return
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER, on=who)
    c.resist(10, DamageType.FIRE, until=When.ENCOUNTER, on=who)
    struck: dict[int, int] = {}

    def bite(victim: int) -> None:
        if struck.get(victim) == c.world.round or victim not in c.enemies():
            return
        struck[victim] = c.world.round
        c.flat(c.int_mod, dtype=DamageType.FIRE, on=victim)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def dusk(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    held = c.world.get(ring, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.extend(
            [
                c.world.bus.on(ZoneEntered, walked_in),
                c.world.bus.on(TurnEnd, dusk),
            ]
        )
    c.note(f"{c.ref}: the target also has partial concealment, and there is none here")


@power(
    "p16281",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p16281(c: Cast) -> None:
    """The secondary is its own block, `p16281b`: a burst 2 on the primary
    rolling Fortitude where this one rolled Reflex. It is an Effect line, so
    it happens whether the first blow landed or not."""
    primary = c.target
    if primary is None:
        return
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.COLD)
    c.use_power("p16281b", on=primary, spend=False)


@power(
    "p192",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ACID, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p192(c: Cast) -> None:
    """Falling prone inside the slime is a `ConditionApplied`, which names its
    subject `target` rather than `actor` -- `about_me` would be false forever
    on it."""
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.ACID)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.ACID)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.hazard(
        area, 5, DamageType.ACID, label=c.ref, until=When.SUSTAIN,
        sustain=MINOR, difficult=True,
    )

    def stumbled(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.PRONE:
            return
        if ev.target in c.world.zones.occupants(zone):
            c.flat(5, dtype=DamageType.ACID, on=ev.target)

    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.append(c.world.bus.on(ConditionApplied, stumbled))


@power(
    "p2375",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.RADIANT],
    attack=Attack(INT, vs=REF),
)
def p2375(c: Cast) -> None:
    """"Gains no benefit from invisibility, nor can it become hidden" is the
    `HIDDEN_FROM` relations it is the hidden end of: cleared, and then kept
    clear -- a fresh one is undone as it is set. Concealment proper has no
    state in this engine, so that third of the sentence is only a note.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.RADIANT)
        c.blinded(until=When.EONT)
    held = c.effect(f"{c.ref} exposed", until=When.SAVE_ENDS)
    if held is None:
        return
    c.world.relations.clear_source(Relation.HIDDEN_FROM, victim, c.ref)

    def spotted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.HIDDEN_FROM and ev.source == victim:
            c.world.relations.clear(Relation.HIDDEN_FROM, victim, ev.target, c.ref)

    held.subs.append(c.world.bus.on(RelationSet, spotted, owner=c.me))
    if c.first:
        c.note(f"{c.ref}: concealment is also denied, and there is none here")


@power(
    "p3219",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p3219(c: Cast) -> None:
    """The burn and the opening ride one effect and one saving throw, which is
    what "save ends both" means. The printed deletion takes out "you and", so
    the advantage is the allies' and not the caster's."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d10", c.int_mod, dtype=DamageType.PSYCHIC)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=(5, DamageType.PSYCHIC),
        relations=[(Relation.GRANTS_CA_TO, victim, a) for a in c.allies()],
    )


@power(
    "p4074",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(5, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ILLUSION, Keyword.ZONE],
    attack=Attack(INT, vs=WILL),
)
def p4074(c: Cast) -> None:
    """The zone is the origin square alone and the pull is toward it. The
    second printed stanza -- the same pull made again -- is `p4074b` now, a
    minor action of its own gated on this zone standing, so sustaining does
    only what sustaining does.
    """
    heart = c.origin or c.here
    if c.first:
        c.zone({heart}, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.pull(4, anchor=heart)
    if victim in c.in_squares(spread({heart}, 1)):
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "p6958",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p6958(c: Cast) -> None:
    """The miss line deals the same damage as the hit, not half: what the roll
    is actually for is the daze. The zone bites enemies only, which is not what
    `c.burns` says, so the latch is written out here.
    """
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)
        c.dazed(until=When.EONT)
    else:
        c.damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)
    struck: dict[int, int] = {}

    def bite(victim: int) -> None:
        if struck.get(victim) == c.world.round or victim not in c.enemies():
            return
        struck[victim] = c.world.round
        c.flat(5, dtype=DamageType.NECROTIC, on=victim)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.extend(
            [
                c.world.bus.on(ZoneEntered, walked_in),
                c.world.bus.on(TurnStart, dawn),
            ]
        )


@power(
    "p11842",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    summon=Summon(
        speed=4, modes=("fly",),
        attack=Attack(INT, vs=REF), damage=Damage("1d8", "int"),
    ),
)
def p11842(c: Cast) -> None:
    """The command's riders -- ongoing poison, and the imp turning invisible
    -- hang off a standard action nothing offers, so only its attack line is
    declared. Hovering has nowhere to go, and the symbiosis is not gated on
    the imp still standing.
    """
    made = c.summon_inline(get(c.ref).summon, at=c.origin)
    if made:
        c.resist(5, DamageType.FIRE, on=made)

    def symbiosis(ev: Hit) -> None:
        if ev.attacker == c.me and c.had_advantage(ev):
            c.damage("1d6", dtype=DamageType.POISON, on=ev.target)

    c.watch(Hit, symbiosis, until=When.ENCOUNTER, label=f"{c.ref} symbiosis")


@power(
    "p11843",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    summon=Summon(
        speed=4, attack=Attack(INT, vs=REF),
        damage=Damage("1d10", "int", dtype=DamageType.FIRE),
    ),
)
def p11843(c: Cast) -> None:
    """Speed 8 while charging is a second speed there is nowhere to put, and
    the ongoing fire and the slow are riders on a command nothing offers.
    The move-action shift the symbiosis grants is an action the caster
    gains, and no header field or `Cast` method adds one.
    """
    made = c.summon_inline(get(c.ref).summon, at=c.origin)
    if made:
        c.resist(5, DamageType.FIRE, on=made)

    def symbiosis(ev: Hit) -> None:
        if ev.attacker == c.me and _at_will_or_basic(ev.power):
            c.cannot_shift(on=ev.target, until=When.EOTNT)

    c.watch(Hit, symbiosis, until=When.ENCOUNTER, label=f"{c.ref} symbiosis")


@power(
    "p4078",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE_IMPLEMENT,
    summon=Summon(speed=6, attack=Attack(INT, vs=REF), damage=Damage("2d6", "int")),
)
def p4078(c: Cast) -> None:
    """One `Summon` carries one attack line, so the header holds the standard
    action's 2d6 and the opportunity attack rolls that rather than its own
    1d8. The standard command has no door; both opportunity clauses do.
    """
    made = c.summon_inline(get(c.ref).summon, at=c.origin)
    if not made:
        return
    _commands_on_opportunity(c, made)

    answered: dict[int, int] = {}

    def retort(ev: AttackRolled) -> None:
        if ev.target == made or not _reach_is(ev.power, "melee"):
            return
        if not c.adjacent_to(made, ev.attacker) or ev.attacker not in c.enemies():
            return
        if answered.get(ev.attacker) == c.world.round:
            return
        answered[ev.attacker] = c.world.round
        c.command(made, on=ev.attacker)

    c.watch(AttackRolled, retort, until=When.ENCOUNTER, label=f"{c.ref} maw retort")


@power(
    "p13984",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.SHADOW, Keyword.SUMMONING],
    todo=("cf:wizard-expert-mage",),
)
def p13984(c: Cast) -> None:
    """Which creature is summoned is read off the caster's Expert Mage
    benefit, and that class feature is not in the tree -- so there is no
    block for `summon=` to declare and nothing for `c.summon_inline` to
    place. Everything else on the card is the standard summoning rules the
    engine already applies to a `summon=` line."""
