"""Warden, level 5: the dailies.

Mostly zones, and the four printed shapes of zone are not the same shape.
"Enters or starts its turn there" is `c.hazard`; "ends its turn there" and
"marked enemies that start their turns there" are watches, and "difficult
terrain for your enemies" is a named sort of going that the warden's own
side is exempt from. All four helpers live in the package root.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.query import squares

from . import rough_for_enemies, when_turn_ends_in, when_turn_starts_in

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


@power(
    "p11075",
    level=5,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p11075(c: Cast) -> None:
    """The zone stays centred on the warden, which is an aura.

    **"You and your allies in the zone have concealment" is written now.**
    The old note said it "has no expression", and `c.conceal` has been the
    expression all along -- held by each of them and gated on standing in
    the aura, which is the idiom `p11283` uses for a zone's penalties.

    Read against the aura's **current** occupants, so an ally who steps out
    loses it and one who steps in picks it up. That matters more here than
    on a fixed zone: this aura follows the warden, so the ground under an
    ally changes without the ally moving at all. #1341.

    "Constitution modifier or Wisdom modifier" is the warden's choice, so:
    the better of the two.
    """
    grit = c.aura(1, until=When.ENCOUNTER)
    for friend in [c.me, *(a for a in c.allies() if a != c.me)]:
        c.conceal(
            on=friend,
            until=When.ENCOUNTER,
            when=lambda ctx, w=friend: w in c.world.zones.occupants(grit),
        )
    bite = max(c.con_mod, c.wis_mod)

    def sting(who: int) -> None:
        if c.marked(who):
            c.flat(bite, on=who)

    when_turn_starts_in(c, grit, sting, until=When.ENCOUNTER)


@power(
    "p5115",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=AC),
)
def p5115(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
        c.slide(3)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
        c.slide(1)


@power(
    "p5116",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(STR, vs=REF),
)
def p5116(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.POISON)
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.POISON)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p5117",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.THUNDER,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(STR, vs=REF),
)
def p5117(c: Cast) -> None:
    if c.first:
        c.teleport(5)
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
        c.dazed(until=When.EONT)


@power(
    "p5118",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.COLD, Keyword.ZONE],
    attack=Attack(STR, vs=FORT),
)
def p5118(c: Cast) -> None:
    if c.first:
        c.hazard(
            c.area(), 5, DamageType.COLD, until=When.SUSTAIN, sustain=MINOR
        )
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.COLD)


@power(
    "p5577",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(STR, vs=FORT),
)
def p5577(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        rough_for_enemies(c, spread({c.there}, 1), until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.str_mod)

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power == c.ref:
            return
        rough_for_enemies(
            c, spread(squares(c.world, ev.target), 1), until=When.ENCOUNTER
        )

    c.watch(Hit, on_hit, until=When.ENCOUNTER, once=True)


@power(
    "p9839",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p9839(c: Cast) -> None:
    if c.first:
        swamp = c.zone(
            c.area(), until=When.SUSTAIN, difficult=True, sustain=MINOR
        )

        def bog(who: int) -> None:
            c.slowed(on=who, until=When.SAVE_ENDS)

        when_turn_ends_in(c, swamp, bog, until=When.ENCOUNTER)
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.str_mod)
        c.slowed(until=When.EONT)


@power(
    "p9840",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p9840(c: Cast) -> None:
    if c.first:
        heave = c.zone(
            c.area(), until=When.SUSTAIN, difficult=True, sustain=MINOR
        )

        def topple(who: int) -> None:
            c.prone(on=who)

        when_turn_ends_in(c, heave, topple, until=When.ENCOUNTER)
    if c.strike():
        c.damage(c.w(), c.str_mod)
    else:
        c.half_damage(c.w(), c.str_mod)
    c.prone()


@power(
    "p9844",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9844(c: Cast) -> None:
    """The printed -5 is the marked condition's own -2 deepened, and that -2
    lives in the attack resolver, so this is a further -3 on top of it. The
    resolver judges "does the attack leave me out" against the whole target
    list; a modifier's gate is handed one target at a time, so a burst that
    catches the warden and somebody else is charged the -3 for the somebody
    else. It is the only reading the context allows."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    victim = c.target
    if victim is None:
        return
    deeper = c.penalty(
        "attack", 3, on=victim, until=When.ENCOUNTER,
        when=lambda ctx: c.marked(victim) and ctx.get("target") != c.me,
    )

    def on_turn_end(ev: TurnEnd) -> None:
        if ev.actor == c.me and deeper is not None and c.distance(victim) > 5:
            c.world.effects.end(deeper, "lost sight of the quarry")

    c.watch(TurnEnd, on_turn_end, until=When.ENCOUNTER)


@power(
    "p9846",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p9846(c: Cast) -> None:
    """**"Regeneration has no method of its own" was false** --
    `c.regeneration(while_bloodied=True)` is the verb, and `p4142` and
    `p5393` have both been moved onto it.

    **This row keeps the hand-rolled watch, deliberately.** Its printed
    line is not plain regeneration: "at the start of each of your turns you
    can forgo regaining the 5 hit points to allow a bloodied ally adjacent
    to you to regain them instead" is a *choice taken at the moment the
    regeneration would land*, and `c.regeneration` heals whoever holds it.
    So the watch is where the choice can be offered, which is what the old
    note's second half said and got right. #1341.
    """
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(), c.str_mod)
    if not c.first:
        return

    def regenerate(ev: TurnStart) -> None:
        if ev.actor != c.me or not c.bloodied(c.me):
            return
        beside = [
            a for a in c.within(1, side="ally") if a != c.me and c.bloodied(a)
        ]
        if beside and c.may("pass the healing to an ally", who=c.me, default=False):
            c.heal(5, on=c.choose(beside, "which bloodied ally takes it"))
        else:
            c.heal(5, on=c.me)

    c.watch(TurnStart, regenerate, until=When.ENCOUNTER)
