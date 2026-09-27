"""Druid, level 5: the daily attacks, and the three forms of this tier.

The forms follow `level_1_d.py`: what is written is the minor action the
header describes, with the shape's standing benefits hung on the form
itself. The attack each unlocks is a separate compendium row.

`p16120` is the one row here with a shape of its own: a penalty that deepens
every time the target is hit, to a floor. Five separate penalties would be
five saving throws -- penalties always stack, so "the largest wins" is not
available either -- so it is one hold carrying five `Mod` objects whose
values are written down in place as the blows land.

The four summoning rows of this level are written the way `level_1_d.py`
writes its own: `Summon` in the header, `c.summon_inline` and one `c.command`
in the body, since the printed Effect gives that command as part of using the
power. All four print an Instinctive Effect, which goes on the same header as
`instinctive=` and shares its tail with the rest through `summons.hunt`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Summon,
    When,
    get,
    power,
)
from combat_engine.engine.query import adjacent, has_combat_advantage

from .forms import beast_row, ends_with, in_beast_form, take_beast_form
from .summons import close_on, hunt, nearest, walk_beside

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
BEAST_FORM = "you must be in beast form"


@power(
    "p10370",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.POISON],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p10370(c: Cast) -> None:
    """The standing half asks the shape at the moment of the blow, not when
    the row was used: a druid that drops out of beast form stops slowing
    things and starts again when it changes back."""
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.POISON)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.POISON)
        c.slowed()
    if not c.first:
        return
    me = c.me
    foes = set(c.enemies())

    def bit(ev: Hit) -> None:
        if ev.attacker != me or ev.target not in foes:
            return
        declared = get(ev.power)
        if declared is None or declared.reach.kind != "melee":
            return
        if in_beast_form(c.world, me):
            c.slowed(on=ev.target, until=When.EONT)

    c.watch(Hit, bit, until=When.ENCOUNTER, on=me, label=f"{c.ref} slows")


@power(
    "p10844",
    level=5,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10844(c: Cast) -> None:
    """The attack context carries `opportunity`, which is what makes the
    second half sayable; the Athletics half is a check."""
    shape = take_beast_form(c)
    ends_with(
        c, shape,
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")),
        ),
    )


@power(
    "p10846",
    level=5,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10846(c: Cast) -> None:
    """The climb speed goes in the form itself, which ends it when the shape
    ends -- `c.form` takes the modes for exactly this."""
    shape = take_beast_form(c, modes={"climb": c.speed_of()})
    ends_with(
        c, shape, c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="untyped")
    )


@power(
    "p10848",
    level=5,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10848(c: Cast) -> None:
    """The damage context carries no `advantage` -- that is on the attack
    context -- so the question is asked of the board instead, which is the
    same question a moment later and the only one available here.
    """
    me = c.me

    def open_guard(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            beast_row(ctx)
            and who is not None
            and has_combat_advantage(c.world, me, who)
        )

    shape = take_beast_form(c)
    ends_with(
        c, shape,
        c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=open_guard),
    )


@power(
    "p13517",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13517(c: Cast) -> None:
    """"While adjacent to the target" is a fact about where the ally is
    standing, which the damage context does not carry -- it names who is
    being hit. So the gate reads the board at the moment the damage is
    rolled, which is what lets one modifier follow an ally walking in."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    for friend in c.allies():
        c.bonus(
            "damage", max(1, c.con_mod), on=friend, until=When.ENCOUNTER,
            kind="power",
            when=lambda ctx, f=friend: adjacent(c.world, f, victim),
        )


@power(
    "p13518",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13518(c: Cast) -> None:
    """"Save ends **both**" is one hold and one saving throw, so the combat
    advantage hangs on the immobilisation rather than beside it."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    hold = c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    ca = c.grants_advantage(until=When.SAVE_ENDS, to="team")
    if hold is not None and ca is not None:
        hold.on_end.append(lambda: c.world.effects.end(ca, "the hold ended"))


@power(
    "p13519",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p13519(c: Cast) -> None:
    """"As if he or she had spent a healing surge" is the surge's worth
    without the surge, so it is a heal for that creature's own quarter rather
    than `c.surge`, which would spend one."""
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    pool = sorted(a for a in c.within(5, of=victim, side="ally") if a != c.me)
    friend = c.choose(pool, f"{c.ref}: who is mended") if pool else None
    if friend is not None:
        c.heal(c.surge_value(of=friend), on=friend)


@power(
    "p16120",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p16120(c: Cast) -> None:
    """One hold, five modifiers, and the numbers written down in place.

    `c.penalty` would make an effect per modifier, and a save-ends hold per
    modifier is five saving throws against one printed line. Penalties
    always stack, so laying a deeper one on top adds rather than replaces --
    which is why the values are edited rather than reapplied.
    """
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    floor = -5 if landed else -2
    mods = [Mod(what=what, value=-1, kind="untyped", label=c.ref)
            for what in ("attack", AC.value, FORT.value, REF.value, WILL.value)]
    hold = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        mods=[(victim, m) for m in mods],
    )

    def worsen(ev: Hit) -> None:
        if ev.target != victim or hold.ended:
            return
        for m in mods:
            m.value = max(floor, m.value - 1)

    hold.subs.append(c.world.bus.on(Hit, worsen, owner=c.me))


def _p5371_instinct(c: Cast, who: int) -> None:
    """"It makes its attack against at least one enemy, targeting as many
    enemies as possible. If it can't target any enemies, it moves its speed
    to a square adjacent to an enemy."

    The blast is approximated the way the body approximates it: everything
    within 3 of the creature, one at a time. Where the blast is laid down
    is the choice the clause is about, and `Summon` carries an attack line
    with no shape to place.
    """
    caught = c.within(3, of=who, side="enemy")
    if not caught:
        close_on(c, who)
        return
    for foe in caught:
        c.command(who, on=foe)


@power(
    "p5371",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE],
    summon=Summon(
        speed=6, attack=Attack(WIS, vs=REF),
        damage=Damage("1d8", "wis", dtype=DamageType.FIRE),
        instinctive=_p5371_instinct,
    ),
)
def p5371(c: Cast) -> None:
    """`Summon` carries one attack line and no shape, so the command's close
    blast is written out: everything within 3 of the beetle is commanded
    one at a time. The command is given as part of using the power, which
    is what the printed Effect says; later ones have no action to spend.
    """
    made = c.summon_inline(get(c.ref).summon)
    if not made:
        return
    c.resist(5, DamageType.FIRE, on=made)
    for foe in c.within(3, of=made, side="enemy"):
        c.command(made, on=foe)


def _p5373_instinct(c: Cast, who: int) -> None:
    """"It moves its speed to a square adjacent to the character it guards.
    If it ends adjacent to any enemies, those enemies are marked by it."

    Who it guards is read back off the relation the body laid, which is
    why the body lays one. The marks are hung on the creature rather than
    the summoner, the way the commanded attack's are.
    """
    ward = (c.guarding(of=who) or [c.me])[0]
    walk_beside(c, who, ward)
    for foe in c.within(1, of=who, side="enemy"):
        c.mark(on=foe, by=who, until=When.EONT)


@power(
    "p5373",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    summon=Summon(
        speed=6, attack=Attack(WIS, vs=REF), damage=Damage("1d8", "wis"),
        instinctive=_p5373_instinct,
    ),
)
def p5373(c: Cast) -> None:
    """Who it protects is chosen through the decider and held as a relation
    **on the creature**, because its instinctive effect walks to whoever
    that is and nothing else records the answer. With no decider installed
    the caster comes first in the list, which is the printed first option.

    The printed Immediate Interrupt -- a second command, triggered when an
    enemy beside it swings at the character it guards -- is still not
    written: a summon has no window of its own to take, and `c.watch` on
    the summoner would spend the summoner's.
    """
    made = c.summon_inline(get(c.ref).summon)
    if not made:
        return
    ward = c.world.decide(
        c.me,
        "guard",
        [c.me, *(a for a in sorted(c.allies()) if a != made)],
        f"{c.ref}: who it guards",
    )
    c.guard(on=ward, by=made)
    if c.command(made, on=c.target):
        c.mark(on=c.target, by=made, until=When.EONT)


def _p5374_instinct(c: Cast, who: int) -> None:
    """Charge the nearest enemy nothing else is standing near; else the tail.

    "Without the shift" is why the charge here is a run-in and a command
    rather than the body's `c.shift` followed by a swing. "No creatures
    within 2 squares of it" counts everybody but the enemy itself -- the
    creature about to charge included, so one it is already next to is out
    of the running anyway.
    """
    alone = [
        f
        for f in c.enemies()
        if not [o for o in c.within(2, of=f, side="any") if o != f]
    ]
    for foe in nearest(c, who, alone):
        if c.run_at(foe, who=who):
            c.command(who, on=foe, charge=True)
            return
    hunt(c, who)


@power(
    "p5374",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    summon=Summon(
        speed=7, attack=Attack(WIS, vs=REF), damage=Damage("1d10", "wis"),
        instinctive=_p5374_instinct,
    ),
)
def p5374(c: Cast) -> None:
    """The shift is the panther's own, so it is walked before the swing."""
    made = c.summon_inline(get(c.ref).summon)
    if not made:
        return
    c.shift(3, who=made)
    c.command(made, on=c.target)


def _p9655_instinct(c: Cast, who: int) -> None:
    """The tail, with the attack line's concealment rider on the swing."""

    def veil(foe: int) -> None:
        c.penalty("attack", 2, on=foe, until=When.EONT)

    hunt(c, who, then=veil)


@power(
    "p9655",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    summon=Summon(
        speed=6, modes=("climb",),
        attack=Attack(WIS, vs=REF), damage=Damage("1d8", "wis"),
        instinctive=_p9655_instinct,
    ),
)
def p9655(c: Cast) -> None:
    """"All creatures have concealment from the target" is written as what
    concealment is -- a -2 to that creature's own attack rolls, of the
    concealment kind so two sources do not add. `c.conceal` grants it to a
    creature against everybody, which is the other direction.
    """
    made = c.summon_inline(get(c.ref).summon)
    if made and c.command(made, on=c.target):
        c.penalty("attack", 2, on=c.target, until=When.EONT)
