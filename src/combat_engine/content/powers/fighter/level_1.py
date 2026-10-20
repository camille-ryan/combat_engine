"""Fighter, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Condition,
    Gear,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.grid import Square, distance
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

#: The four holds `f1300`'s clause on `p997` names together.
#:
#: **Copied rather than shared, and that is the convention's stated cost.**
#: `f1300` names four rows and its clause goes into each of their bodies
#: (#550), so this tuple follows it. A shared home was considered and
#: rejected twice over: `content/powers/` importing from `content/feats/`
#: would reverse the import direction the tree already has in eight places,
#: and a general `c.held_fast()` would be one symbol serving several needs --
#: three other files in the tree name *different* held sets for different
#: printed lines, which is why there is no general one.
_HELD_FAST = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)

#: The zone `f1305`'s clause on `p992` reads -- the caster's own `p2473`.
_CLOUD = "p2473"


def _others_in_cloud(c: Cast, hit: int) -> list[int]:
    """"All other enemies within the area" of the caster's own `p2473`.

    Empty unless the creature just hit is standing in it, which is the
    clause's first half. `Cast.zone` labels a zone with the ref that laid
    it when the row passes no `label=`, so that ref is the whole match.

    Copied from `feats/general_h.py`, where `f1305`'s clause on `p87` still
    uses it. **The heaviest duplication this migration has cost so far**,
    and the first one big enough to argue about: fifteen lines of reader,
    not three lines of clause. It takes the creature hit rather than the
    `Hit` event, because a body has `c.target` and no event.
    """
    area: frozenset[Square] = frozenset()
    for _zid, zone in c.world.zones.all():
        if zone.owner == c.me and zone.label == _CLOUD:
            area = zone.squares
            break
    inside = c.in_squares(area, side="enemy") if area else []
    return [] if hit not in inside else [f for f in inside if f != hit]


@power(
    "p997",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p997(c: Cast) -> None:
    """Two feats pay their clause on this row's **miss**, and they stack.

    #550's convention. See `p704` for the grouping rule; in short, the
    compendium brackets a feat's category after its name and Camille's
    rule is one `[Arena Fighting]`, one `[Lesser Style]`, any number of
    unbracketed.

    `f994` is Arena Fighting and is read off `c.declare`, which is called
    before the attack. `f1300` carries no bracket and is a plain `c.feat`
    test that stacks with it. **The first version chained the two**, on a
    family split inferred from the books instead of read from the bracket.

    `c.declare` is called here even though only one Arena Fighting clause
    is written: it is the slot the other four go into, and a body that
    asks `c.feat` today is a body somebody has to remember to convert.

    Both hang on the miss and not the hit, which is unusual and is why
    they sit after the early return: one pays "damage equal to your
    Strength modifier **+2**" where the printed row already pays the
    modifier, and the other pays against a held target whether the blow
    landed or not. Six of this row's eight printed feat clauses are
    miss-clauses, which is unusual enough to be worth saying.

    **Five more Arena Fighting feats and three Lesser Style feats name
    this row and are not written yet**, so `f994` sits alone in a chain
    that will grow and the Lesser Style chain does not exist. `f3230` is
    Arena Fighting and is one of the five; its clause is once per
    encounter, which a body has no latch for, so it cannot come here at
    all.
    """
    arena = c.declare("Arena Fighting", "f994")
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        return
    # A miss still does something, and a two-handed weapon does more.
    c.flat(c.str_mod if c.wielding("two-handed") else c.str_mod // 2)
    # **Two, not Strength modifier + 2.** The line above already pays the
    # modifier on a two-handed miss, so the full printed figure would pay
    # it twice. #299's trap, and the reason this row was read before the
    # clause was written.
    if arena == "f994" and c.wielding("two-handed"):
        c.flat(2, on=c.target)
    # f1300 carries no bracket, so it stacks with the arena feat above
    # rather than being chained to it. This was an `elif` and was wrong.
    if (c.feat("f1300") and c.con_mod > 0
            and any(c.is_(hold, on=c.target) for hold in _HELD_FAST)):
        c.flat(c.con_mod, on=c.target)


@power(
    "p992",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p992(c: Cast) -> None:
    """Three feats hang a clause on this hit and **none of them conflict**.

    #550's convention. `f1299`, `f1304` and `f1305` carry no category
    bracket in the compendium, so nothing limits how many of them apply
    to one use: three plain `if`s.

    **This row was the clearest casualty of my own mistake.** It shipped
    as a three-way `if`/`elif` chain, on the reasoning that all three
    printed names end in the same word -- and the word is not the
    category. The bracket is. A character holding all three was being
    given one clause of the three it is entitled to.

    `f3188`, `f977`, `f987` and `f993` are Arena Fighting and `f2356` and
    `f2714` are Lesser Style. **`f993` is written now (#780)** and is the
    whole of the Arena Fighting chain; the other three and both Lesser
    Styles still want theirs.

    **`f993` trades this row's damage for temporary hit points, and the
    trade needed no new verb.** Its marker said a row cannot decline its
    own damage. `c.strike()` rolls and does not pay -- the body pays, with
    `c.damage` -- so declining is not calling it. Only `f3188`, `f977` and
    `f987` are left off the `c.declare` list, because their clauses are
    not written and a declaration that picks a feat paying nothing is
    worse than no declaration.

    **Which damage.** The card says "forgo dealing damage to an adjacent
    enemy", and on a Melee 1 row both the creature struck *and* the second
    one caught by the splash are adjacent, so the phrase does not settle
    it on its own. Read as the damage dealt to the creature this use hit --
    the attack's own damage, which is what "forgo dealing damage" means
    everywhere else it is printed. The splash is a separate printed clause
    of this power rather than anything the feat speaks to, so it still
    lands. Said out loud because it is a reading and not a transcription.

    **The board cannot see the traded branch.** `c.choose` takes its first
    option here, and the first option is dealing the damage -- the printed
    behaviour with no feat applied, which is the right default. So the
    audit exercises the ordinary path and `drivers.damage_forgone_for_a_rider`
    is what exercises the trade.
    """
    arena = c.declare("Arena Fighting", "f993")
    if not c.strike():
        return
    traded = (arena == "f993" and c.adjacent()
              and c.choose([False, True],
                           "forgo the damage for temporary hit points"))
    if traded:
        c.temp_hp(c.con_mod, on=c.me)
    else:
        c.damage(c.w(1), c.str_mod)
    # And a second enemy beside you takes the modifier on its own.
    others = [e for e in c.within(1, side="enemy") if e != c.target]
    if others:
        c.flat(c.str_mod, on=c.choose(others, "who else does it catch"))

    foe = c.target
    if foe is None:
        return
    # **All three carry no bracket, so all three stack.** This was written
    # as one chain and that was wrong: the compendium tags a feat's category
    # in brackets after its name, and these have none, so nothing limits
    # how many of them apply to one use.
    if (c.feat("f1299") and c.wis_mod > 0
            and not any(o != foe for o in c.within(1, of=foe, side="enemy"))):
        c.ongoing(c.wis_mod, on=foe)
    if c.feat("f1304"):
        c.mark(on=foe)
    if c.feat("f1305") and c.str_mod > 0:
        for other in _others_in_cloud(c, foe):
            c.flat(c.str_mod, on=other)


@power(
    "p1000",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=lambda world, eid: _has_shield(world, eid),
    requires_text="needs a shield",
)
def p1000(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        def push_and_follow() -> None:
            vacated = c.there
            if c.push(1):
                # step into the space it was driven out of
                c.shift(to=vacated)

        c.instead_of("push", push_and_follow)


@power(
    "p1758",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=2),
)
def p1758(c: Cast) -> None:
    """No ability modifier on the damage: the +2 to hit is what it buys.

    **Three feats of the exclusive category name this row and only two of
    them could come here**, which is the first time #550's convention has
    failed to deliver its main promise. `f978` and `f985` are the chain;
    `f981` is still a rider in `feats/exploits.py` and **stacks with
    whichever of these pays**, which the printed rule does not allow.

    Why it could not move: `f981`'s clause asks whether the target has
    damaged the character *since the end of their last turn*. That is a
    memory, not a question about the board, and it has to be armed before
    the blow it remembers -- `_riders` arms it through `setup=` when the
    trait arms at the start of the fight. A body runs far too late: the
    damage happened already, so a set built here is empty by construction
    and the clause would silently pay nothing. `_hurt_me_since`'s own
    docstring records that as how the first attempt at it failed.

    So this row's exclusivity is **partial and the instrument says so** --
    `drivers.py at_most_one_applies` carries `f981` as a known rider and
    skips rather than claiming the chain is complete. #556 is the fix:
    promote that memory into the engine, where nothing has to arm it.

    The two that did move are read off `c.declare`, called before the
    attack, so the choice between them cannot depend on the roll.

    `f1102` and six others also name this row in other categories and
    stack legitimately.
    """
    arena = c.declare("Arena Fighting", "f978", "f985")
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1))

    # **The gear read sits INSIDE the branch, and that is not tidiness.**
    # `chargen._does_more_than_damage` asks whether a body does anything
    # beyond rolling damage, by reading the source and skipping clauses
    # gated on `c.feat`. A `c.world` read above the gate is *not* skipped,
    # so this row -- whose card is a plain "+2 to hit, no ability modifier
    # on the damage" -- scored as a rider row and the draw moved. A line
    # that only one feat's clause needs belongs in that clause.
    #
    # `c.my_weapon()` is the wrong verb here and was my first try: it
    # means "the weapon *this row's item* sits on", which a class power
    # has none of, so it answered None and this branch could never pay.
    # The row is melee-only, so the main hand is the weapon swung, which
    # is what `c.weapon_of` picked off the event before the clause moved.
    if arena == "f978" and c.wielding("superior"):
        gear = c.world.get(c.me, Gear)
        weapon = gear.main if gear is not None else None
        if weapon is not None:
            c.flat(weapon.proficiency, on=c.target)
    elif arena == "f985" and c.wielding("shield"):
        c.bonus(AC, 1, on=c.me, until=When.EONT, kind="feat")


def _has_shield(world: object, eid: int) -> bool:
    from combat_engine.engine import Gear

    gear = world.get(eid, Gear)  # type: ignore[attr-defined]
    return bool(gear and gear.shield)


# -- encounter --------------------------------------------------------------


@power(
    "p1004",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1004(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.prone()


@power(
    "p1008",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1008(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slowed()
        # Slowed leaves shifting alone, so the second half of the line is a
        # real extra. Immobilised would stop walking too and is the wrong card.
        c.note(f"p1008: {c.target} also could not shift until the end of your next turn")


@power(
    "p1015",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1015(c: Cast) -> None:
    """Two swings at two creatures, and the step is what joins them.

    The header carries the primary line, which is what a policy reads; the
    secondary rolls longhand because it has its own bonus.

    The shift is aimed rather than handed to the world's shift decider, which
    knows nothing about the swing that follows and will happily walk out of
    reach of it. The second creature is picked first, from anything a single
    step can reach, and the step goes to a square beside it. The shift is
    printed as optional, so standing still is allowed when the follow-up is
    already in reach.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    primary = c.target
    pool = [e for e in c.within(2, side="enemy") if e != primary]
    second = c.choose(pool, "who the follow-up catches") if pool else None
    if second is None:
        c.shift(1)  # the step is granted whether or not there is a second swing
        return
    if not c.adjacent(second):
        beside = squares_of(c.world, second)
        steps = [
            s
            for s in c.world.reachable_squares(c.me, 1)
            if any(distance(s, f) <= 1 for f in beside)
        ]
        if steps:
            c.shift(1, to=steps[0])
    if c.attack(c.str_ + 2, AC, on=second):
        c.damage(c.w(1), c.str_mod, on=second)


@power(
    "p1427",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1427(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        # "An ally of yours": the caster is not one of them.
        friends = [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
        if friends:
            c.shift(2, who=c.choose(friends, "who gets clear"))


# -- daily ------------------------------------------------------------------


@power(
    "p1431",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1431(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.surge(on=c.me)


@power(
    "p1524",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1524(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
