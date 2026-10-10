"""Theme powers, fifteen themes, keyed by each theme's alias ref.

Two readings run through the whole batch and both are judgement calls, so
they are here rather than repeated in sixty docstrings.

**"Highest ability modifier"** is a number, not a blank: it is the best of
the six, and `_best`/`_best_mod` say exactly that. The *header* is where it
cannot be said -- `Attack` takes one `Ability` and there is no word for
"whichever is largest" -- so those rows carry no `attack=` line and roll
longhand in the body, the way `cleric/level_1_d.py` rolls "Strength or
Wisdom". The cost is that a policy reads no attack line off the card; the
row itself is exact.

**"Primary ability"** is a different sentence and a real gap. The primary is
`chargen.Build.primary`, which a `Cast` cannot reach, and nothing on the
board records which class took the theme. Those rows carry
`c.ability_for(ref)` -- the marker 21 rows already wait on -- as a `todo`
where the attack is the row and a `dropped` where the row has a working
half.

`cls` is the theme's alias ref for the same reason a racial power is keyed
by the race: a printed name in that column would leak, and a word shaped
like a class would be dealt to every character of it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    REGISTRY,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Health,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    Pick,
    Powers,
    PowerUsed,
    Ranged,
    RoundStart,
    SkillCheck,
    Square,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    about_me,
    both,
    by_charge,
    by_me,
    by_melee,
    by_ranged,
    distance,
    get,
    my_check,
    power,
    query,
    targets_me,
)

DEFENCES = (AC, FORT, REF, WILL)

#: The one marker this batch names again and again: which ability a theme
#: row attacks with, decided per character rather than per card.
ABILITY = ("c.ability_for(ref)",)


def _primary(c: Cast) -> int:
    """"Primary ability vs. X" as an attack bonus, for a **secondary** attack.

    A row whose own action is the attack declares it in the header and reads
    `c.attack_mod`. `p12262`'s attack is printed inside its Effect as an
    interrupt held for later, on a `PERSONAL` row with no attack line to be,
    so `c.primary` and the per-ability property are joined up here. The same
    helper is in `batch_d.py`, kept local to each file because a parallel
    author edits one file and not the tree.
    """
    return {
        Ability.STR: c.str_,
        Ability.CON: c.con_,
        Ability.DEX: c.dex_,
        Ability.INT: c.int_,
        Ability.WIS: c.wis_,
        Ability.CHA: c.cha_,
    }[c.primary]


def _best(c: Cast) -> int:
    """"Highest ability modifier vs. X" as a rolled bonus.

    `c.str_` and its five siblings are each the whole attack bonus -- half
    level, the modifier, proficiency where the row is a weapon row, and the
    enhancement in hand -- so the largest of the six *is* the printed line.
    """
    return max(c.str_, c.con_, c.dex_, c.int_, c.wis_, c.cha_)


def _best_mod(c: Cast) -> int:
    """The bare modifier, for the damage and effect lines."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _beside(c: Cast, foe: int) -> list[Square]:
    """Squares next to `foe` that are also a step from where I stand."""
    near = query.spread(query.squares(c.world, foe), 1)
    return sorted(near & query.spread(query.squares(c.world, c.me), 1))


def _spent_encounter_attacks(c: Cast, cap: int = 30) -> list[str]:
    """Expended rows that are encounter *attack* powers of level <= cap.

    `c.expended` returns refs and nothing else, so the usage, the attack
    line and the level are read back off the registry -- the same lookup
    `Cast._declared` makes.
    """
    out = []
    for ref in c.expended():
        p = REGISTRY.get(ref)
        if p is None or p.attack is None:
            continue
        if p.usage is Usage.ENCOUNTER and p.level <= cap:
            out.append(ref)
    return out


# ---------------------------------------------------------------- x7_661


@power(
    "p12258",
    level=0,
    cls="x7_661",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p12258(c: Cast) -> None:
    """Thunder on a hit, and a mark that punishes being ignored.

    **The mark is an Effect, not a Hit clause**, so it lands whether or not
    the attack did -- the stub's docstring said it hung off the hit, which
    the card does not.

    The punish watches `PowerUsed` rather than `AttackDeclared`, and that is
    the whole of the care here. An attack is announced **once per target**,
    so a burst that leaves the marker out would pay the 5 thunder once for
    every creature it did catch; `leaves_me_out` exists because two marks
    had that bug the other way round. `PowerUsed` fires once per use and
    carries the whole target list, which is the question the card asks.
    """
    if c.strike():
        c.damage(c.w(1), c.attack_mod, dtype=DamageType.THUNDER)
    foe = c.target
    if foe is None:
        return
    c.mark(until=When.EONT)

    def ignored(ev: PowerUsed) -> None:
        if ev.actor != foe or c.me in (ev.targets or ()):
            return
        row = get(ev.power)
        if row is None or not row.is_attack:
            return
        c.flat(5, on=foe, dtype=DamageType.THUNDER)

    c.watch(PowerUsed, ignored, until=When.EONT, on=foe, label=c.ref)


@power(
    "p12259",
    level=2,
    cls="x7_661",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def p12259(c: Cast) -> None:
    """The allies' concealment follows adjacency rather than being handed
    to whoever happened to be beside you at the moment of the shift, which
    is what the printed "while they are adjacent to you" says."""
    c.shift(3)
    c.conceal(on=c.me, until=When.EONT)
    for friend in c.allies():
        c.conceal(
            on=friend,
            until=When.EONT,
            when=lambda ctx, f=friend: c.adjacent_to(c.me, f),
        )


@power(
    "p12260",
    level=6,
    cls="x7_661",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL],
)
def p12260(c: Cast) -> None:
    """A flight the caster's own ability measures, and a push on the melee
    hits that follow it.

    `c.primary_mod` is "your primary ability modifier" -- the caster's, even
    though the flier may be an ally, because the card measures the distance by
    the one who used the power.

    Flight is a mode plus a move, which is the shape `p6990` uses: the mode
    ends with the turn and `movement.settle` puts the creature down, which is
    the printed landing.

    The push names `by=` the flier. `c.push` measures away from the caster's
    square by default and the enemy is being shoved by whoever hit it, which
    on this row is usually somebody else.
    """
    who = c.target
    if who is None:
        return
    reach = max(1, c.primary_mod)
    c.mode("fly", reach, until=When.EOT, on=who)
    c.move(reach, who=who)

    def shove(ev: Hit) -> None:
        if ev.attacker != who or not by_melee(c.world, who, ev):
            return
        c.push(1, on=ev.target, by=who)

    c.watch(Hit, shove, until=When.EONT, on=who)


@power(
    "p12261",
    level=10,
    cls="x7_661",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.ZONE],
    dropped=("c.vulnerable_in()",),
)
def p12261(c: Cast) -> None:
    """"Each ally in the burst" leaves the caster out, so the row is aimed at
    nobody and asks the board instead -- `EACH_ALLY` would have included him
    and the surge would then ride on there being an ally to target at all."""
    c.surge(on=c.me)
    for friend in c.within(3, side="ally"):
        c.temp_hp(c.level // 2, on=friend)
    c.zone(c.area(), label=c.ref, until=When.EONT)


@power(
    "p12262",
    level=3,
    cls="x7_661",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[
        Keyword.POLYMORPH,
        Keyword.PRIMAL,
        Keyword.THUNDER,
        Keyword.WEAPON,
    ],
)
def p12262(c: Cast) -> None:
    """A form, resistance, and one interrupt held for an adjacent enemy that
    moves.

    **`MoveStart` is the right event twice over.** It is the interrupt window
    -- by `MoveEnd` the enemy has left and `c.adjacent` is false exactly when
    the row should fire -- and it is also what "moves **willingly**" means:
    `movement.forced` steps straight through `movement.step` and announces no
    `MoveStart` at all, so a shove never opens this window.

    "Once before the end of your next turn", so the watcher spends itself.
    """
    c.form(until=When.EONT, label=c.ref)
    c.resist(5, until=When.EONT, on=c.me)
    fired = [False]

    def gore(ev: MoveStart) -> None:
        foe = ev.actor
        if fired[0] or foe not in c.enemies() or not c.adjacent(foe):
            return
        fired[0] = True
        if c.attack(_primary(c), FORT, on=foe):
            c.damage(c.w(2), c.primary_mod, dtype=DamageType.THUNDER, on=foe)
            c.prone(on=foe)

    c.arm_trigger(
        MoveStart,
        gore,
        cost=ActionType.IMMEDIATE_INTERRUPT,
        until=When.EONT,
        on=c.me,
        label=c.ref,
    )


@power(
    "p12263",
    level=7,
    cls="x7_661",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH, Keyword.PRIMAL, Keyword.WEAPON],
)
def p12263(c: Cast) -> None:
    """"Immune to forced movement" is `c.immovable`.

    The blast the form unlocks is a second card filed under this same ref.
    It is `p12263b` now and declared below, so the form hands it over --
    "once before the end of your next turn" is `uses=1` on the grant, and
    the card's own Requirement keeps it unusable once the form drops."""
    c.form(until=When.EONT, label=c.ref)
    c.immovable(until=When.EONT, on=c.me)
    c.grant_row("p12263b", on=c.me, until=When.EONT, uses=1)


@power(
    "p12264",
    level=5,
    cls="x7_661",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[
        Keyword.POLYMORPH,
        Keyword.PRIMAL,
        Keyword.THUNDER,
        Keyword.WEAPON,
    ],
)
def p12264(c: Cast) -> None:
    """"Each enemy that starts its turn within 2 squares" is an aura plus a
    `TurnStart` watcher, because the payout is on the enemy's turn and not
    on entry.

    "Once during the encounter while in this form, you can use the Attack
    power" is the grant: `p12264b`, once."""
    c.form(until=When.ENCOUNTER, label=c.ref)
    c.grant_row("p12264b", on=c.me, until=When.ENCOUNTER, uses=1)
    c.aura(2, label=c.ref, until=When.ENCOUNTER, on=c.me)

    def scorch(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.flat(5, dtype=DamageType.THUNDER, on=ev.actor)
        c.mark(on=ev.actor, until=When.EONT)

    c.watch(TurnStart, scorch, until=When.ENCOUNTER, label=f"{c.ref} roar")


@power(
    "p12265",
    level=9,
    cls="x7_661",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH, Keyword.PRIMAL, Keyword.WEAPON],
)
def p12265(c: Cast) -> None:
    """The resistance carries a live adjacency gate, so an ally who steps up
    later is covered. `c.immovable` takes no gate, so that half is laid on
    whoever is beside you when the form is assumed.

    The form's own attack is `p12265b`, handed over once."""
    c.form(until=When.ENCOUNTER, label=c.ref)
    c.grant_row("p12265b", on=c.me, until=When.ENCOUNTER, uses=1)
    c.resist(5, until=When.ENCOUNTER, on=c.me)
    c.immovable(until=When.ENCOUNTER, on=c.me)
    for friend in c.allies():
        c.resist(
            5,
            until=When.ENCOUNTER,
            on=friend,
            when=lambda ctx, f=friend: c.adjacent_to(c.me, f),
        )
        if c.adjacent_to(c.me, friend):
            c.immovable(until=When.ENCOUNTER, on=friend)


# ---------------------------------------------------------------- x7_885

MARTIAL_PRIMAL = [Keyword.MARTIAL, Keyword.PRIMAL]


@power(
    "p14312",
    level=0,
    cls="x7_885",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*MARTIAL_PRIMAL, Keyword.FEAR],
    trigger="you hit an enemy with a charge attack",
    on=Trigger(Hit, both(by_me, by_charge), "you hit an enemy with a charge"),
)
def p14312(c: Cast) -> None:
    """The extra die lands on the triggering enemy once, not once per enemy
    caught in the burst, which is what `c.first` is for."""
    if c.first:
        c.damage("1d6", on=c.trigger.target)
    if c.attack(_best(c), WILL):
        c.push(2)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p14313",
    level=2,
    cls="x7_885",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL_PRIMAL,
    out_of_combat=True,
)
def p14313(c: Cast) -> None:
    """The whole benefit is "roll twice on an Athletics or Endurance check",
    which is a skill bonus and nothing else -- the same shape as a cantrip
    that lights a room."""
    c.note(c.ref)


@power(
    "p14314",
    level=3,
    cls="x7_885",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_PRIMAL, Keyword.WEAPON],
)
def p14314(c: Cast) -> None:
    """Both results are kept because the shift is gated on the pair, so the
    first cannot be branched on and forgotten."""
    first = bool(c.attack(_best(c), REF))
    if first:
        c.damage(0, _best_mod(c))
        c.prone()
    second = bool(c.attack(_best(c), AC))
    if second:
        c.damage(c.w(2), _best_mod(c))
    if first and second:
        c.shift(2)


def _shifted_beside_me(world: World, me: int, ev: MoveEnd) -> bool:
    """An enemy that shifted and is still within a step and a half.

    The printed line is "an enemy **adjacent to you** shifts", which wants
    the square it left; `Moved` is the only event carrying `from_` and it
    does not carry `kind_`, so this asks `MoveEnd` where it has landed.
    """
    if ev.kind_ != "shift" or ev.actor == me:
        return False
    if ev.actor not in query.enemies(world, me):
        return False
    return query.distance_between(world, me, ev.actor) <= 2


@power(
    "p14317",
    level=6,
    cls="x7_885",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL_PRIMAL,
    trigger="an enemy adjacent to you shifts 1 square",
    on=Trigger(MoveEnd, _shifted_beside_me, "an enemy beside you shifts"),
    dropped=("Moved.kind_",),
)
def p14317(c: Cast) -> None:
    """The destination is named rather than chosen -- "to a square adjacent
    to that enemy" is an instruction. The trigger is the dropped clause: it
    fires on where the enemy landed instead of where it started."""
    foe = c.trigger.actor
    for sq in _beside(c, foe):
        if c.shift(1, to=sq):
            break
    c.bonus(
        "attack",
        2,
        kind="power",
        until=When.EONT,
        on=c.me,
        once=True,
        when=lambda ctx, f=foe: ctx.get("target") == f,
    )


@power(
    "p14318",
    level=7,
    cls="x7_885",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[*MARTIAL_PRIMAL, Keyword.WEAPON, Keyword.FEAR],
    trigger="you hit an enemy with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def p14318(c: Cast) -> None:
    """The secondary is aimed off the board rather than declared, because
    the row is `NO_TARGET`: the primary comes off the trigger and the
    secondary is explicitly somebody else."""
    first = c.trigger.target
    c.prone(on=first)
    c.shift(3)
    others = [foe for foe in c.within(1, side="enemy") if foe != first]
    victim = c.choose(others)
    if victim is None:
        return
    if c.attack(_best(c), AC, on=victim):
        c.damage(c.w(2), on=victim)
        c.push(2, on=victim)
        c.penalty("attack", 2, on=victim, until=When.EONT)


def _crit_on_me(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and ev.critical


def _bloodied_by_a_foe(world: World, me: int, ev: Bloodied) -> bool:
    """`Bloodied` names its subject `actor`, so `targets_me` is false on it
    forever; `source` is whoever crossed the line and may be nobody."""
    return ev.actor == me and ev.source in query.enemies(world, me)


@power(
    "p14321",
    level=10,
    cls="x7_885",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL_PRIMAL,
    trigger="an enemy bloodies you or scores a critical hit against you",
    on=(
        Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"),
        Trigger(Hit, _crit_on_me, "an enemy crits you"),
    ),
)
def p14321(c: Cast) -> None:
    """"Until you have no temporary hit points left" is not a duration the
    engine has, so the bonus is held to the encounter and gated on the temp
    pool still being there when the roll is made."""
    c.temp_hp(c.level + _best_mod(c), on=c.me)

    def still_padded(ctx: dict[str, Any]) -> bool:
        health = c.world.get(c.me, Health)
        return bool(health and health.temp > 0) and not ctx.get("ranged", False)

    c.bonus(
        "attack",
        2,
        kind="power",
        until=When.ENCOUNTER,
        on=c.me,
        when=still_padded,
    )


# ---------------------------------------------------------------- x7_853


@power(
    "p14131",
    level=0,
    cls="x7_853",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.WEAPON],
)
def p14131(c: Cast) -> None:
    """The ally line is an Effect, so it is paid whether or not the swing
    landed. "+2 bonus to all defenses" prints no type word: untyped."""
    if c.attack(_best(c), AC):
        c.damage(c.w(), _best_mod(c))
    friend = c.choose(c.within(3, side="ally"))
    if friend is None:
        return
    for d in DEFENCES:
        c.bonus(d, 2, on=friend, until=When.EONT)
    c.temp_hp(3 + c.level // 2, on=friend)


@power(
    "p14132",
    level=0,
    cls="x7_853",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
)
def p14132(c: Cast) -> None:
    if c.attack(_best(c), WILL):
        c.damage("1d8", _best_mod(c), dtype=DamageType.RADIANT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p14134",
    level=2,
    cls="x7_853",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p14134(c: Cast) -> None:
    """`EACH_ALLY`'s pool is the allies **and** the caster, which is the
    printed "You and each ally in the burst"."""
    c.save()
    c.heal(10 if c.bloodied() else 5)


@power(
    "p14135",
    level=6,
    cls="x7_853",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
)
def p14135(c: Cast) -> None:
    """Everything runs on the first target because the effect ends for the
    whole group when any one of them attacks, so the bonuses have to be
    held together. Sustaining re-lays them."""
    if not c.first:
        return
    crowd = list(c.targets)
    held: list[tuple[int, Any]] = []

    def arm() -> None:
        held.clear()
        for who in crowd:
            for d in DEFENCES:
                held.append((who, c.bonus(d, 5, kind="power", on=who, until=When.EONT)))

    def broke(ev: AttackDeclared) -> None:
        if ev.attacker not in crowd:
            return
        for who, eff in held:
            c.end_effect(eff, on=who)
        held.clear()

    arm()
    carrier = c.effect(c.ref, until=When.SUSTAIN, sustain=STANDARD, on=c.me)
    c.on_sustain(carrier, arm)
    c.watch(AttackDeclared, broke, until=When.ENCOUNTER, label=f"{c.ref} break")


@power(
    "p14136",
    level=10,
    cls="x7_853",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.ZONE],
    dropped=("c.surge_bonus()",),
)
def p14136(c: Cast) -> None:
    """The radiant burn is undead-only, which `c.burns` cannot say, so it is
    a `TurnEnd` watcher guarded on the zone still standing. The surge-value
    clause has no verb at all."""
    area = c.area()
    ring = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    for d in DEFENCES:
        c.grants_in(ring, d, 2, side="team", kind="untyped")

    def sear(ev: TurnEnd) -> None:
        if ev.ghost or ring not in c.my_zones():
            return
        if not c.is_kind("undead", on=ev.actor):
            return
        if query.squares(c.world, ev.actor) & area:
            c.flat(5, dtype=DamageType.RADIANT, on=ev.actor)

    c.watch(TurnEnd, sear, until=When.ENCOUNTER, label=f"{c.ref} light")


# ---------------------------------------------------------------- x7_852


@power(
    "p14127",
    level=0,
    cls="x7_852",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT],
)
def p14127(c: Cast) -> None:
    if c.attack(_best(c), WILL):
        c.damage("1d8", _best_mod(c), dtype=DamageType.RADIANT)
        c.dazed(until=When.EONT)


@power(
    "p14128",
    level=2,
    cls="x7_852",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p14128(c: Cast) -> None:
    c.invisible(on=c.me, until=When.EOT)


@power(
    "p14129",
    level=6,
    cls="x7_852",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def p14129(c: Cast) -> None:
    """The flight is granted for the turn and then walked, which is how a
    fly speed is spent; "and land" is the mode lapsing at the end of it."""
    c.mode("fly", 6, until=When.EOT, on=c.me)
    c.no_provoke(on=c.me, until=When.EOT)
    c.move(6)


@power(
    "p14130",
    level=10,
    cls="x7_852",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
    dropped=("spec.stat_block()",),
    narrative=("skill:insight",),
)
def p14130(c: Cast) -> None:
    """The movement modes come from a beast the player picks, and no block
    for it was given, so `c.form(modes=)` has nothing to be handed.

    The Insight clause is the narrative one: it is a DC for an observer
    deciding whether the shape looks supernatural, which is a question
    nothing on a board ever asks.
    """
    c.form(until=When.EONT, revert=MINOR, label=c.ref)
    c.cannot_attack(on=c.me, until=When.EONT)


# ---------------------------------------------------------------- x7_862


@power(
    "p14167",
    level=0,
    cls="x7_862",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    charges=True,
)
def p14167(c: Cast) -> None:
    """`charges=True` because the Effect *is* a move-then-hit: without it
    the reach is measured before the walk and the row is refused against
    anything further off than a sword.

    "At any point during your move" is resolved as move-then-attack, which
    is the only ordering the engine can run.
    """
    c.no_provoke(from_=c.target, on=c.me, until=When.EOT)
    c.move(c.speed_of())
    if c.attack(_best(c), REF):
        c.damage(c.w(), _best_mod(c))
        c.slowed(until=When.EONT)


def _missed_me_nearby(world: World, me: int, ev: Miss) -> bool:
    if ev.target != me or ev.attacker == me:
        return False
    if ev.attacker not in query.enemies(world, me):
        return False
    return query.distance_between(world, me, ev.attacker) <= 5


@power(
    "p14168",
    level=2,
    cls="x7_862",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    trigger="an enemy within 5 squares of you misses you with an attack",
    on=Trigger(Miss, _missed_me_nearby, "an enemy nearby misses you"),
)
def p14168(c: Cast) -> None:
    """"Until it hits you" is not a duration, so the penalty runs to the end
    of the encounter and a watcher takes it off the moment it lands one."""
    foe = c.trigger.attacker
    shame = c.penalty("attack", 2, on=foe, until=When.ENCOUNTER)

    def paid(ev: Hit) -> None:
        if ev.attacker == foe and ev.target == c.me:
            c.end_effect(shame, on=foe)

    c.watch(Hit, paid, until=When.ENCOUNTER, label=f"{c.ref} debt")


@power(
    "p14169",
    level=6,
    cls="x7_862",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def p14169(c: Cast) -> None:
    """The count is taken **when the attack is declared**, which is a window
    that turned out to exist: `resolve.attack` emits `AttackDeclared` with
    the roll as its continuation, so a listener runs before the defence is
    ever read and a number only knowable then can still be laid.

    **Re-aimed away from `c.bonus(value=)`,** which was never the gap -- the
    parameter has always been there and a fixed number was the wrong shape,
    not a missing one.

    `window=Window.BEFORE` is load-bearing and `c.watch`'s default is the
    reaction window, which runs *after* the continuation -- the bonus was
    laid and read too late, and the row looked finished with a delta of
    nought.

    Laid against `ev.vs` rather than five times over: that is the one
    defence this attack reads, and `once=True` spends the hold on it so
    "against that attack" does not outlive the attack."""

    def braced(ev: AttackDeclared) -> None:
        if ev.target != c.me:
            return
        crowd = len(c.within(1, side="enemy"))
        if crowd:
            c.bonus(ev.vs, crowd, on=c.me, until=When.EOT, kind="power", once=True)

    c.watch(AttackDeclared, braced, until=When.EONT, window=Window.BEFORE,
            label=f"{c.ref} brace")

    def dodged(ev: Miss) -> None:
        if ev.target == c.me:
            c.grant_action("shift", FREE, squares_=1, on=c.me, until=When.EOT)

    c.watch(Miss, dodged, until=When.EONT, label=f"{c.ref} slip")


def _pinned_down(world: World, eid: int) -> bool:
    held = (Condition.RESTRAINED, Condition.SLOWED, Condition.IMMOBILIZED)
    if any(query.is_(world, eid, cond) for cond in held):
        return True
    return any(query.flanked_by(world, eid, foe) for foe in query.enemies(world, eid))


@power(
    "p14170",
    level=10,
    cls="x7_862",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_pinned_down,
    requires_text="restrained, slowed, immobilized, or flanked",
)
def p14170(c: Cast) -> None:
    """One effect, not all three: the first of the conditions that is
    actually holding you is the one that comes off."""
    for cond in (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED):
        if c.is_(cond, on=c.me) and c.end_effect(on=c.me, carrying=cond):
            break
    c.shift(3)


# ---------------------------------------------------------------- x7_876


@power(
    "p14221",
    level=0,
    cls="x7_876",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy with an attack"),
)
def p14221(c: Cast) -> None:
    """The recoil is aimed at the caster; `c.flat` follows `c.target`, which
    on a `NO_TARGET` row is nobody, so it has to be named."""
    c.dazed(on=c.trigger.target, until=When.EONT)
    c.flat(5 + c.level // 2, on=c.me)


@power(
    "p14222",
    level=2,
    cls="x7_876",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("c.recharge_roll()",),
)
def p14222(c: Cast) -> None:
    """The penalty is laid on each enemy with a live "am I inside" gate, so
    a creature that walks in later is covered and one that walks out is
    not. Nothing touches a recharge roll."""
    c.aura(2, label=c.ref, until=When.EONT, on=c.me)
    for foe in c.enemies():
        c.penalty(
            "attack",
            2,
            on=foe,
            until=When.EONT,
            when=lambda ctx, f=foe: c.in_my_aura(f, label=c.ref),
        )


@power(
    "p14223",
    level=6,
    cls="x7_876",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you are targeted by a melee or a ranged attack",
    on=(
        Trigger(AttackDeclared, both(targets_me, by_melee), "a melee attack"),
        Trigger(AttackDeclared, both(targets_me, by_ranged), "a ranged attack"),
    ),
)
def p14223(c: Cast) -> None:
    """Two declared triggers rather than one, because "melee or ranged" is
    two predicates and a close burst is neither."""
    attacker = c.trigger.attacker
    near = [x for x in c.within(1) if x not in (c.me, attacker)]
    victim = c.choose(near)
    if victim is not None:
        c.redirect(to=victim)


def _advantaged_hit(world: World, me: int, ev: Hit) -> bool:
    if ev.attacker != me:
        return False
    return bool(getattr(getattr(ev, "result", None), "advantage", False))


@power(
    "p14224",
    level=10,
    cls="x7_876",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you hit an enemy granting combat advantage to you",
    on=Trigger(Hit, _advantaged_hit, "you hit with combat advantage"),
)
def p14224(c: Cast) -> None:
    """The Requirement -- every encounter attack power already spent -- is
    checked here rather than in the predicate: it is a fact about the sheet
    and not about the event being answered."""
    kit = c.world.get(c.me, Powers)
    known = list(getattr(kit, "known", ()) or ())
    spent = set(c.expended())
    for ref in known:
        p = REGISTRY.get(ref)
        if p is None or p.attack is None or p.usage is not Usage.ENCOUNTER:
            continue
        if ref not in spent:
            return
    back = c.choose(_spent_encounter_attacks(c, cap=7))
    if back is not None:
        c.restore_use(back)


# ---------------------------------------------------------------- x7_925


@power(
    "p15944",
    level=0,
    cls="x7_925",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.FIRE, Keyword.NECROTIC],
)
def p15944(c: Cast) -> None:
    """The backlash is the same clause seen from the other side, so one flag
    decides both: the `TurnEnd` watcher only bites if the `Hit` watcher
    never did."""
    landed: list[bool] = []

    def scorch(ev: Hit) -> None:
        if ev.attacker != c.me or landed:
            return
        landed.append(True)
        c.flat(
            5,
            dtypes=(DamageType.FIRE, DamageType.NECROTIC),
            on=ev.target,
        )
        c.slide(5, on=ev.target)

    def recoil(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != c.me or landed:
            return
        c.flat(5, dtypes=(DamageType.FIRE, DamageType.NECROTIC), on=c.me)

    c.watch(Hit, scorch, until=When.EOT, label=f"{c.ref} brand")
    c.watch(TurnEnd, recoil, until=When.EOT, label=f"{c.ref} recoil")


@power(
    "p15945",
    level=2,
    cls="x7_925",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FIRE],
)
def p15945(c: Cast) -> None:
    """"The first creature to hit" and "the first creature to miss" are two
    separate firsts, so they are two watchers and two flags."""
    victim = c.target
    blessed: list[bool] = []
    burnt: list[bool] = []

    def rewarded(ev: Hit) -> None:
        if ev.target != victim or blessed:
            return
        blessed.append(True)
        c.temp_hp(3 + c.level // 2, on=ev.attacker)

    def punished(ev: Miss) -> None:
        if ev.target != victim or burnt:
            return
        burnt.append(True)
        c.flat(c.roll("1d10"), dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, rewarded, until=When.EONT, label=f"{c.ref} boon")
    c.watch(Miss, punished, until=When.EONT, label=f"{c.ref} bane")


@power(
    "p15946",
    level=6,
    cls="x7_925",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION, Keyword.ZONE],
    dropped=("c.vulnerable_in()", "c.conceal_in()"),
)
def p15946(c: Cast) -> None:
    """The zone and the teleport stand; a zone cannot yet hold either a
    vulnerability or concealment for whoever is inside it."""
    c.zone(c.area(), label=c.ref, until=When.EONT)
    c.teleport(5)


@power(
    "p15947",
    level=10,
    cls="x7_925",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    trigger="you kill a nonminion creature",
    on=Trigger(Dropped, by_me, "you drop a creature"),
)
def p15947(c: Cast) -> None:
    """`Dropped` carries `source`, which is what `by_me` reads, and `actor`
    is the creature that fell -- so the minion test asks `actor`."""
    if c.is_minion(on=c.trigger.actor):
        return
    back = _spent_encounter_attacks(c)
    pick = c.choose(["surge", *(["power"] if back else [])])
    if pick == "power":
        chosen = c.choose(back)
        if chosen is not None:
            c.restore_use(chosen)
            return
    c.surge(on=c.me)


# ---------------------------------------------------------------- x7_943


@power(
    "p16057",
    level=0,
    cls="x7_943",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL],
    trigger="you hit with a melee attack on your turn",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def p16057(c: Cast) -> None:
    """"Randomly determined" is a die, and `c.roll` is the only randomness a
    body is allowed -- so the neighbour is picked off a d(n)."""
    if c.turn_of() != c.me:
        return
    near = [x for x in c.within(1) if x != c.me]
    if not near:
        return
    victim = near[c.roll(f"1d{len(near)}") - 1]
    c.damage("1d6", on=victim)


@power(
    "p16058",
    level=2,
    cls="x7_943",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL],
    )
def p16058(c: Cast) -> None:
    """Advantage on melee attacks against a bloodied enemy, and darkvision.

    Both of the advantage's narrowings are per swing -- the shape of the
    power, and whether the enemy is bloodied *at the moment the attack is
    made* -- and `c.gains_advantage` is asked then rather than when the power
    is used.

    The darkvision lasts the encounter, as the card prints it."""
    from combat_engine.engine.dsl import get

    def melee_at_the_bloodied(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", ""))
        return (
            row is not None and row.reach.kind == "melee"
            and c.bloodied(on=ctx["target"])
        )

    c.gains_advantage(melee_at_the_bloodied, until=When.ENCOUNTER, on=c.me)


@power(
    "p16059",
    level=6,
    cls="x7_943",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL],
    trigger="you make an attack roll and miss",
    on=Trigger(Miss, by_me, "you miss with an attack"),
    dropped=("c.provokes_from()",),
)
def p16059(c: Cast) -> None:
    """"Use either result" is `keep="best"`. Nothing makes a creature's own
    allies provoke from it, which is the price half of the card."""
    c.reroll_attack(keep="best")


@power(
    "p16060",
    level=10,
    cls="x7_943",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.ELEMENTAL],
    trigger="you reduce a creature to 0 hit points on your turn",
    on=Trigger(Dropped, by_me, "you drop a creature"),
)
def p16060(c: Cast) -> None:
    """"Grants combat advantage" with nobody named means to everyone, and
    the relation names one beneficiary at a time -- so it is laid once per
    creature on the other side of whichever target this is."""
    if c.turn_of() != c.me:
        return
    who = c.target
    if who in c.enemies():
        c.grants_advantage(on=who, to="team", until=When.EONT)
    else:
        for foe in c.enemies():
            c.grants_advantage(on=who, to=foe, until=When.EONT)
    c.bonus(
        "damage",
        0,
        dice="1d8",
        on=who,
        until=When.EONT,
        when=lambda ctx: not ctx.get("ranged", False),
    )


# ---------------------------------------------------------------- x7_955


@power(
    "p16113",
    level=0,
    cls="x7_955",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.ELEMENTAL, Keyword.WEAPON],
    charges=True,
)
def p16113(c: Cast) -> None:
    """Same shape as any move-and-hit row, so `charges=True`; the flight is
    a mode granted for the turn and then spent."""
    pace = c.speed_of()
    c.mode("fly", pace, until=When.EOT, on=c.me)
    c.move(pace)
    if c.attack(_best(c), AC):
        c.damage(c.w(), _best_mod(c))
        c.slide(1)


@power(
    "p16114",
    level=2,
    cls="x7_955",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL],
    dropped=("c.aura(difficult=)",),
)
def p16114(c: Cast) -> None:
    """The bonus is against ranged attacks only, which the attack context
    carries, and only while inside -- so both go in one gate. An aura
    cannot be difficult terrain; only a zone can."""
    c.aura(2, label=c.ref, until=When.EONT, on=c.me)
    for who in (c.me, *c.allies()):
        for d in (AC, REF):
            c.bonus(
                d,
                2,
                kind="power",
                on=who,
                until=When.EONT,
                when=lambda ctx, w=who: ctx.get("ranged", False)
                and c.in_my_aura(w, label=c.ref),
            )


@power(
    "p16115",
    level=6,
    cls="x7_955",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ANY_CREATURE,
    keywords=[Keyword.ELEMENTAL, Keyword.ILLUSION],
)
def p16115(c: Cast) -> None:
    """"If the target makes an attack, the invisibility ends" is a watcher
    rather than a duration; sustaining lays it again."""
    who = c.target
    held: list[Any] = []

    def hide() -> None:
        held.clear()
        held.append(c.invisible(on=who, until=When.EONT))

    def seen(ev: AttackDeclared) -> None:
        if ev.attacker != who:
            return
        for eff in held:
            c.end_effect(eff, on=who)
        held.clear()

    hide()
    carrier = c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR, on=c.me)
    c.on_sustain(carrier, hide)
    c.watch(AttackDeclared, seen, until=When.ENCOUNTER, label=f"{c.ref} reveal")


@power(
    "p16116",
    level=10,
    cls="x7_955",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL],
)
def p16116(c: Cast) -> None:
    """`c.hover` is the "and can hover" half: it lifts the creature and puts
    it in an airborne movement state, which is what stops the fall."""
    c.mode("fly", 8, until=When.EONT, on=c.me)
    c.hover(8, on=c.me, until=When.EONT)


# ---------------------------------------------------------------- x7_983


@power(
    "p16411",
    level=0,
    cls="x7_983",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("c.grant_armor()",),
)
def p16411(c: Cast) -> None:
    """Conjuring a suit of +1 armour onto a creature mid-fight: nothing puts
    a worn item on anybody. `c.grant_weapon()` is the other half of the
    same absence and is already a marker group."""
    ...


def _surprised_at_the_off(world: World, me: int, ev: RoundStart) -> bool:
    if ev.round != 1:
        return False
    return query.is_(world, me, Condition.SURPRISED) and query.conscious(world, me)


@power(
    "p16412",
    level=2,
    cls="x7_983",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you are surprised at the start of an encounter while conscious",
    on=Trigger(RoundStart, _surprised_at_the_off, "you are surprised"),
)
def p16412(c: Cast) -> None:
    """There is no "encounter begins" event, so the surprise round is round
    one; a move action is what is granted, and the action ladder already
    lets a move be spent as a minor."""
    c.extra_action(MOVE, on=c.me)


@power(
    "p16413",
    level=6,
    cls="x7_983",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def p16413(c: Cast) -> None:
    """A Diplomacy check treated as a natural 20 and nothing else."""
    c.note(c.ref)


@power(
    "p16414",
    level=10,
    cls="x7_983",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger="you make an Intimidate check against a creature you can see",
    on=Trigger(SkillCheck, my_check("intimidate"), "you intimidate somebody"),
    dropped=("c.suppress(keyword=)",),
)
def p16414(c: Cast) -> None:
    """The bonus is laid after the die because the trigger is the roll, which
    is what `c.boost_check` is for. Suspending an effect by keyword and
    letting it resume has no verb -- `c.end_effect` is final."""
    c.boost_check(2)


# ---------------------------------------------------------------- x7_992


@power(
    "p16525",
    level=0,
    cls="x7_992",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.forbid(keyword=)",),
)
def p16525(c: Cast) -> None:
    """`revert=None` and `c.endable` instead of `c.form(revert=MINOR)`,
    because leaving the form is not a bare exit -- it is a minor action
    that also shifts you a square.

    Two clauses have no verb: low-light vision, and barring every power that
    lacks a keyword. The third used to be the at-will attack the form
    unlocks -- it is `p12263b`'s sibling `p16525b` now, declared below.
    """
    shape = c.form(until=When.ENCOUNTER, revert=None, label=c.ref)
    c.endable(shape, MINOR, then=lambda: c.shift(1))
    c.low_light(until=When.ENCOUNTER)


@power(
    "p16525b",
    level=0,
    cls="x7_992",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(Pick.HIGHEST, plus=3, vs=AC),
    dropped=("c.form(class_form=)",),
)
def p16525b(c: Cast) -> None:
    """The attack the form unlocks, which is a **second card filed under
    p16525's own ref**.

    It had no ref of its own until `parse_extra` was called for theme powers,
    and without one it could not be declared -- so p16527's grab rider was
    armed and waiting on a hit that nothing could ever make. Declaring it is
    what makes that rider reachable.

    "Highest ability modifier" is `Pick.HIGHEST`, the rule the header says
    and `c.mod(c.ability_for())` answers in the body -- not `Pick.PRIMARY`,
    which is a different sentence that only accidentally agrees.
    """
    if not c.strike():
        return
    c.damage("1d8", c.mod(c.ability_for()))
    c.mark(until=When.SONT)


def _wearing(ref: str):  # noqa: ANN202
    """"The power <ref> must be active in order to use this power."

    The form is recorded as an effect labelled with the ref that laid it --
    the same question `p16528` asks -- so the requirement is that label
    standing on the caster. A factory because three rows in this run print
    the identical line about their own parent.
    """
    def active(world: World, eid: int) -> bool:
        return any(e.label.startswith(ref) for e in world.effects.of(eid))

    return active


@power(
    "p12263b",
    level=7,
    cls="x7_661",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POLYMORPH, Keyword.PRIMAL, Keyword.WEAPON],
    attack=Attack(Pick.PRIMARY, vs=REF),
    requires=_wearing("p12263"),
    requires_text="the p12263 form must be active",
)
def p12263b(c: Cast) -> None:
    """The blast p12263's form unlocks -- the second card inside its entry.

    It had no ref until `parse_extra` was called for theme powers, so the
    parent could not hand it over and the row could not be declared. Both
    halves are here now: this card, and the grant on the parent.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.attack_mod)
    c.push(2)
    c.blinded(until=When.EONT)


@power(
    "p12264b",
    level=5,
    cls="x7_661",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.POLYMORPH, Keyword.PRIMAL, Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(Pick.PRIMARY, vs=REF),
    requires=_wearing("p12264"),
    requires_text="the p12264 form must be active",
)
def p12264b(c: Cast) -> None:
    """The burst p12264's form unlocks. Same shape as p12263b above."""
    if not c.strike():
        return
    c.damage(c.w(1), c.attack_mod, dtype=DamageType.THUNDER)
    c.slide(1)
    c.slowed(until=When.SAVE_ENDS)


@power(
    "p12265b",
    level=9,
    cls="x7_661",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.POLYMORPH, Keyword.PRIMAL, Keyword.WEAPON],
    attack=Attack(Pick.PRIMARY, vs=FORT),
    requires=_wearing("p12265"),
    requires_text="the p12265 form must be active",
)
def p12265b(c: Cast) -> None:
    """The burst p12265's form unlocks. "Each enemy in the burst you can
    see" is `EACH_ENEMY` plus the sight check, which the targeting does."""
    if not c.strike():
        return
    c.damage(c.w(2), c.attack_mod)
    c.weakened(until=When.EONT)


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and 0 < health.hp <= health.max_hp // 2


@power(
    "p16527",
    level=2,
    cls="x7_992",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="you must have started this turn bloodied",
)
def p16527(c: Cast) -> None:
    """The requirement is read as "bloodied now" -- nothing records what you
    were at the top of the turn.

    The grab rides on p16525's second card, which **has a ref now**:
    `p16525b` was parsed all along and never imported, because only the class
    pass asked a parent for its extras and this is a theme power.

    "Beast Form" is not one of the engine's keywords, so only Healing is
    declared.
    """
    me = c.me

    def caught(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "power", "") == "p16525b":
            c.grab(on=ev.target, by=me)

    c.watch(Hit, caught, until=When.ENCOUNTER, on=me, label=c.ref)
    c.regeneration(2, until=When.ENCOUNTER, on=c.me, while_bloodied=True)


@power(
    "p16528",
    level=6,
    cls="x7_992",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger="an attack hits you while you are not in your beast form",
    on=Trigger(Hit, targets_me, "an attack hits you"),
)
def p16528(c: Cast) -> None:
    """"While you are not in your beast form" is asked of the label p16525
    lays, which is the only record that the shape is on."""
    if c.me in c.suffering("p16525", include_self=True):
        return
    c.use_power("p16525", again=True)
    for foe in c.within(3, side="enemy"):
        if c.can_see(foe):
            c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)


@power(
    "p16529",
    level=10,
    cls="x7_992",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL],
)
def p16529(c: Cast) -> None:
    c.end_effect(on=c.target, save_ends=True)


# --------------------------------------------------------------- x7_1005


@power(
    "p16592",
    level=0,
    cls="x7_1005",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
)
def p16592(c: Cast) -> None:
    """The save is narrowed to the immobilising effect by name, so it does
    not shake off something the card never offered."""
    c.save(on=c.me, against="immobilized")
    c.shift(2)
    if c.attack(_best(c), AC):
        c.damage(c.w(), _best_mod(c))


@power(
    "p16593",
    level=2,
    cls="x7_1005",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    out_of_combat=True,
)
def p16593(c: Cast) -> None:
    """A Bluff reroll, and an initiative bonus for a fight that has not
    started -- neither half happens on a board."""
    c.note(c.ref)


def _drow_or_spider(c: Cast):  # noqa: ANN202
    """The damage context names the creature being hit as `target`; an
    out-of-band total carries no such key, so the gate reads it rather than
    indexing it."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and (
            c.is_kind("drow", on=who) or c.is_kind("spider", on=who)
        )

    return gate


@power(
    "p16594",
    level=6,
    cls="x7_1005",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p16594(c: Cast) -> None:
    """The damage bonus asks the creature's kinds, which the damage context
    carries as `target` -- so the narrowing to two sorts of enemy is a real
    gate rather than a line in a docstring."""
    c.stance(on=c.me, label=c.ref)
    for d in DEFENCES:
        c.bonus(d, 2, kind="power", on=c.me, until=When.STANCE)
    c.bonus(
        "damage",
        _best_mod(c),
        kind="power",
        on=c.me,
        until=When.STANCE,
        when=_drow_or_spider(c),
    )


@power(
    "p16595",
    level=10,
    cls="x7_1005",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def p16595(c: Cast) -> None:
    """The Prerequisite is a build-time gate and not this row's to enforce;
    what is checked here is the printed "if it is not expended"."""
    c.shift(c.speed_of())
    if c.knows("p2473") is not None and "p2473" not in c.expended():
        c.use_power("p2473")


# --------------------------------------------------------------- x7_1019


def _melee_or_ranged(ref: str) -> bool:
    p = REGISTRY.get(ref)
    return p is None or p.reach.kind in ("melee", "ranged")


@power(
    "p16679",
    level=0,
    cls="x7_1019",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.STANCE],
    dropped=("OpportunityWindow.why",),
)
def p16679(c: Cast) -> None:
    """"Melee or ranged attack" excludes a burst, and the `Hit` names the row
    that threw it, so the reach is read back off the registry rather than
    guessed.

    The defence bonus can only ask whether the blow was an opportunity
    attack; the attack context does not carry *why* the window opened, so
    "that you provoke by moving" is the dropped narrowing.
    """
    c.stance(on=c.me, label=c.ref)

    def brand(ev: Hit) -> None:
        if ev.attacker != c.me or not _melee_or_ranged(ev.power):
            return
        if ev.target in c.enemies():
            c.mark(on=ev.target, until=When.EONT)

    c.watch(Hit, brand, until=When.STANCE, label=f"{c.ref} brand")
    for d in DEFENCES:
        c.bonus(
            d,
            2,
            kind="power",
            on=c.me,
            until=When.STANCE,
            when=lambda ctx: ctx.get("opportunity", False),
        )


@power(
    "p16680",
    level=2,
    cls="x7_1019",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p16680(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "p16681",
    level=6,
    cls="x7_1019",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p16681(c: Cast) -> None:
    """Three different clocks on one card: the initiative bonus is instant,
    the speed and attack bonuses die when any enemy acts, and the defences
    die when one lands a blow -- so each set is ended by its own watcher."""
    c.initiative(5, on=c.me)
    early = [
        c.bonus("speed", 2, kind="power", on=c.me, until=When.ENCOUNTER),
        c.bonus("attack", 2, kind="power", on=c.me, until=When.ENCOUNTER),
    ]
    guard = [
        c.bonus(d, 2, kind="power", on=c.me, until=When.ENCOUNTER) for d in DEFENCES
    ]

    def acted(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        for eff in early:
            c.end_effect(eff, on=c.me)
        early.clear()

    def struck(ev: Hit) -> None:
        if ev.target != c.me:
            return
        for eff in guard:
            c.end_effect(eff, on=c.me)
        guard.clear()

    c.watch(TurnStart, acted, until=When.ENCOUNTER, label=f"{c.ref} dash")
    c.watch(Hit, struck, until=When.ENCOUNTER, label=f"{c.ref} poise")


@power(
    "p16682",
    level=10,
    cls="x7_1019",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.STANCE],
    dropped=("c.ignore_squeeze_penalty()",),
    narrative=("skill:acrobatics",),
)
def p16682(c: Cast) -> None:
    """Climbing at full speed is a movement mode. Squeezing at full speed is
    a real gap and already a marker group.

    Balancing is the narrative clause: the circumstance is crossing a
    narrow ledge, and an Acrobatics check to stay upright on one is never
    rolled on a board, so the speed it would be crossed at has nowhere to
    go and nothing is missing.
    """
    c.stance(on=c.me, label=c.ref)
    c.ignores_difficult(on=c.me, until=When.STANCE)
    c.mode("climb", c.speed_of(), until=When.STANCE, on=c.me)


# ---------------------------------------------------------------- x7_937


@power(
    "p16018",
    level=2,
    cls="x7_937",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def p16018(c: Cast) -> None:
    """`c.jump` rather than `c.move`: ground crossed rather than walked, and
    the distance does not come out of the turn's movement."""
    c.jump(c.speed_of())
    foe = c.choose(c.within(1, side="enemy"))
    if foe is not None:
        c.grants_advantage(on=foe, to=c.me, until=When.EONT, once=True)


@power(
    "p16019",
    level=6,
    cls="x7_937",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    dropped=("c.no_conceal_in()",),
)
def p16019(c: Cast) -> None:
    """Seeing the unseen is a sense of the caster's and that half is exact.
    "Creatures in the aura cannot benefit from concealment" is about
    everybody inside it, including two enemies looking at each other, and
    an aura cannot hold that."""
    c.aura(1, label=c.ref, until=When.ENCOUNTER, on=c.me)
    c.see_invisible(on=c.me, until=When.ENCOUNTER)


def _fled_from_me(world: World, me: int, ev: Moved) -> bool:
    """An enemy that was within 10 and has moved further off than it was."""
    if ev.actor == me or ev.actor not in query.enemies(world, me):
        return False
    mine = query.squares(world, me)
    if not mine:
        return False
    was = min(distance(ev.from_, sq) for sq in mine)
    now = min(distance(ev.to, sq) for sq in mine)
    return was <= 10 and now > was


@power(
    "p16020",
    level=10,
    cls="x7_937",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.TELEPORTATION],
    trigger="an enemy that started its turn within 10 squares ends it farther away",
    on=Trigger(Moved, _fled_from_me, "an enemy backs away from you"),
    dropped=("query.distance_at_turn_start()",),
)
def p16020(c: Cast) -> None:
    """The printed trigger is measured across a whole turn; `Moved` is the
    only event carrying where the creature came from, so the row fires on
    one step away instead of on the turn's net distance.

    The teleport names its square, which is how it ignores line of sight.
    """
    foe = c.trigger.actor
    for sq in sorted(query.spread(query.squares(c.world, foe), 1)):
        if c.teleport(c.distance(foe) + 1, to=sq):
            return


# --------------------------------------------------------------- x7_1017


@power(
    "p16671",
    level=2,
    cls="x7_1017",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def p16671(c: Cast) -> None:
    """Rolling a Diplomacy check in place of an ally's. Nothing on a board
    ever asks for one."""
    c.note(c.ref)


@power(
    "p16672",
    level=6,
    cls="x7_1017",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def p16672(c: Cast) -> None:
    """Swapping an Intimidate check for a Diplomacy one when talking an
    opponent into surrendering: a negotiation, not a fight."""
    c.note(c.ref)


@power(
    "p16673",
    level=10,
    cls="x7_1017",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    todo=("c.cannot_act(during=)",),
)
def p16673(c: Cast) -> None:
    """The check is sayable and its consequence is not: "cannot take actions
    **during your turn**" is a bar that is on for one creature's turn and
    off for the rest, which is neither stunned nor dazed nor
    `c.cannot_attack`. With the consequence gone there is no half of this
    row left that does anything."""
    ...
