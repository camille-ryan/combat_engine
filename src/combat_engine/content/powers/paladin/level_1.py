"""Paladin, level 1 -- and the one class feature that is not already written.

`p805`, `p1566` and `p1747` are the paladin's other features and live in
`content/features/defenders.py`, declared there before this file existed. A
ref may only be declared once, so they are not repeated here.
"""

from __future__ import annotations

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    When,
    power,
)
from combat_engine.engine.events import AttackDeclared

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _marked_by_me(c: Cast) -> bool:
    """"If you marked the target" -- by *you*, not by whoever got there first.

    `c.is_(Condition.MARKED)` answers a different question: it is true of a
    creature the fighter next to you marked, and these powers pay out on your
    own mark only.
    """
    if c.target is None:
        return False
    return c.world.relations.holds(Relation.MARKED_BY, c.me, c.target)


# -- at-will ----------------------------------------------------------------


@power(
    "p1567",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p1567(c: Cast) -> None:
    """The radiant swing, and `f1097`'s rider written in.

    **It is here now rather than registered from the feat**, which is
    #550's convention: a feat naming one power has its clause in that
    power, gated on `c.feat` and wrapped in `c.credit` so the effect the
    power lays is still the feat's doing. `p4542` is the worked pair.

    This docstring used to warn the opposite -- that the clause already
    lived in `feats/general_g` through the older `_riders` shape, so
    writing it in as well would hand the neighbour its damage bonus
    **twice**. That warning was right while the rider stood; the rider is
    deleted in the same change as this, which is the only way the pair can
    be correct at once. The lesson it recorded is unchanged: grep for the
    ref before writing a clause into a row.

    **The clause goes before `c.damage`, where the rider used to fire.**
    `_riders` hung it on `Hit`, which is announced inside `c.strike()` --
    so the rider ran before this body resumed, and keeping that order
    costs nothing and preserves what a reader of the log sees. Nothing in
    it reads the damage, so the placement is about faithfulness rather
    than about the result.

    `f1097` is **unbracketed** (`feat.category` is empty in `game.db`), so
    a plain `if` and not a `c.declare` chain. Its other two clauses are
    laid at arming and stay on the feat row -- see `f1097` for why neither
    is a clause a body could carry.

    `c.allies()` is `query.allies(world, me)` exactly, which is what the
    rider called; the first adjacent friend takes it, as before. The card
    says "one ally adjacent to you", so adjacency is measured from the
    caster and not from the target."""
    if c.strike():
        if c.feat("f1097") and c.is_kind("undead"):
            with c.credit("f1097"):
                # "If your target is undead, one ally adjacent to you gains
                # a bonus to its next damage roll against the target equal
                # to your Wisdom modifier." `once=True` is "its next", and
                # the gate is "against the target".
                foe = c.target
                for friend in c.allies():
                    if c.adjacent(to=friend):
                        c.bonus(
                            "damage", c.wis_mod, on=friend,
                            until=When.ENCOUNTER, once=True,
                            when=lambda ctx: ctx.get("target") == foe,
                        )
                        break
        bonus = c.str_mod + (c.wis_mod if _marked_by_me(c) else 0)
        c.damage(c.w(1), bonus, dtype=DamageType.RADIANT)

@power(
    "p833",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p833(c: Cast) -> None:
    """The temporary hit points, or `f1098`'s save in lieu of them.

    **Written in rather than registered, which is #550's convention** and
    not what this row's feat note proposed. That note said the clause is
    `c.pre_empt` and the line owed was `p833` asking
    `c.instead_of("temp_hp", ...)` -- the older rider shape, which
    `content/CLAUDE.md` says the tree "still holds in places". #550
    replaced it for a feat naming **one** power, and the reason is in that
    file: the rider shape only reached a power written to *ask*, and almost
    none were -- 36 registrations against 12 read sites.

    So the gate is `c.feat` and the branch is here. `f1098` is unbracketed
    (`feat.category` is empty in `game.db`), so a plain `if`.

    `c.save(on=c.me, against="ongoing")` is the card's "a saving throw
    against any necrotic ongoing effects": `against=` picks which save-ends
    effect, and without it the throw would take whichever it found first --
    "which may well be a daze when the row means the burn", as that verb's
    own docstring puts it. The necrotic narrowing is not sayable there, so
    this is the ongoing-damage save and the type is the approximation.

    `c.may`, because the card says "you can", and declining leaves the
    printed temporary hit points standing."""
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        if (c.feat("f1098") and c.is_kind("undead")
                and c.may("save against an ongoing effect instead of"
                          " gaining temporary hit points")):
            with c.credit("f1098"):
                c.save(on=c.me, against="ongoing")
            return
        c.temp_hp(c.wis_mod, on=c.me)


@power(
    "p835",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p835(c: Cast) -> None:
    """The more of them there are, the better this swings.

    The header's attack line is the printed one, for the card and for a
    policy to read; the body rolls its own, because the bonus is a count of
    the board and the header is data.

    **Two feats name this row and both clauses are written in** (#550):
    `f1100`'s bonus to Will and `f1102`'s extra damage per adjacent
    undead. Both are **unbracketed** (`feat.category` is empty in
    `game.db` for each), so they are two independent plain `if`s rather
    than a `c.declare` chain -- the chain is only for the bracketed
    categories, where one feat per bracket applies to one use, and these
    two stack legitimately with each other and with the row.

    **Both go before `c.damage`, where their riders used to fire.**
    `_riders` hung each on `Hit`, which is announced inside `c.attack()`,
    so a rider ran before this body resumed. For `f1100` that is
    immaterial; for `f1102` it is not, because `c.flat` deals a separate
    blow rather than adding to the roll -- paying it after the swing would
    land it on a creature this row may just have dropped.
    """
    if c.attack(c.str_ + len(c.within(1, side="enemy")), AC):
        if c.feat("f1102"):
            with c.credit("f1102"):
                # "You gain a +1 bonus to your damage roll for each undead
                # enemy adjacent to you." Counted at the blow, because
                # people move.
                near = sum(
                    1 for foe in c.enemies()
                    if c.adjacent(to=foe) and c.is_kind("undead", on=foe)
                )
                if near:
                    c.flat(near, on=c.target)
        if (c.feat("f1100") and c.is_kind("undead")
                and c.marked(on=c.target)):
            with c.credit("f1100"):
                # "If you hit an undead creature with this prayer and it is
                # marked by you, you gain a +1 bonus to Will until the
                # start of your next turn." `c.marked` is "by you" unless
                # told otherwise, which is the printed word.
                c.bonus(WILL, 1, on=c.me, until=When.SONT)
        c.damage(c.w(1), c.str_mod)


@power(
    "p836",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p836(c: Cast) -> None:
    """The printed -2, and `f1099`'s swap written in rather than registered.

    **#550's convention.** A feat that names one power writes its clause
    into that power, gated on `c.feat`, and the feat row stays declared as
    a pointer -- which is why `f1099` carries `implemented_in=("p836",)`
    now instead of a marker. `p704` is the worked example.

    `f1099` is **unbracketed** (`feat.category` is empty in `game.db`), so
    it is a plain `if` and not a `c.declare` chain: the chain is only for
    the bracketed categories, where one feat per bracket applies to one
    use.

    **`c.may`, because the card says "you can".** The swap is offered at
    the hit rather than imposed, and an unanswered offer leaves the printed
    penalty standing -- which is why the branch returns rather than falling
    through to it.

    `to="enemies"` on the target: "grant combat advantage" with nobody
    named means to everybody attacking it, and the target's enemies are
    this side. `c.grants_advantage(on=X)` is "X grants", `to=` is who
    gains, and the default `"me"` would have said the target grants
    advantage to itself.
    """
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        if not _marked_by_me(c):
            return
        if (c.feat("f1099") and c.is_kind("undead")
                and c.may("forgo the attack penalty to make it grant"
                          " combat advantage")):
            with c.credit("f1099"):
                c.grants_advantage(on=c.target, to="enemies", until=When.SONT)
            return
        c.penalty("attack", 2)


# -- encounter --------------------------------------------------------------


@power(
    "p218",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p218(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.mark()
        others = [e for e in c.within(1, side="enemy") if e != c.target]
        for _ in range(max(0, c.wis_mod)):
            if not others:
                break
            who = c.choose(others, "who else do you mark")
            others.remove(who)
            c.mark(on=who)


@power(
    "p358",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p358(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p684",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(CHA, vs=AC),
)
def p684(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.penalty("attack", c.wis_mod)


@power(
    "p755",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p755(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    if c.first:
        # The Effect line lands whether the swing did or not.
        friends = [a for a in c.within(5, side="ally") if a != c.me]
        if friends:
            c.bonus(AC, c.wis_mod, on=c.choose(friends, "who gets the warding"), kind="power")


# -- daily ------------------------------------------------------------------


@power(
    "p2258",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p2258(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    # Hit or miss, somebody nearby gets to spend a surge.
    friends = [a for a in c.within(5, side="ally") if a != c.me]
    hurt = [a for a in friends if c.wounded(a)]
    if hurt or friends:
        c.surge(on=c.choose(hurt or friends, "who spends a healing surge"))


@power(
    "p1268",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p1268(c: Cast) -> None:
    """Attacking costs it, once a round, until it shakes this off.

    Hit and miss leave the same arrangement behind at different sizes, so the
    watcher is written once and the die is the only difference.
    """
    hit = c.strike()
    if hit:
        c.damage("3d8", c.cha_mod)
    else:
        c.half_damage("3d8", c.cha_mod)

    victim, die = c.target, "1d8" if hit else "1d4"
    struck: dict[int, int] = {}

    def recoil(ev: AttackDeclared) -> None:
        if ev.attacker != victim or c.world.turn != victim:
            return  # its own attacks, on its own turn
        if struck.get(victim) == c.world.round:
            return  # once per round, and no more
        struck[victim] = c.world.round
        c.flat(c.world.rng.roll(die).total, on=victim)

    c.watch(AttackDeclared, recoil, until=When.SAVE_ENDS, label=f"{c.ref} recoil")


@power(
    "p1273",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p1273(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.penalty(AC, 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
    c.dazed()  # both lines daze, so it sits outside the branch


# -- class feature ----------------------------------------------------------


@power(
    "p1746",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    # "One creature in the burst", and it means it: this is spent on a
    # friend nine times in ten. `ONE_CREATURE` is the *enemy* pool, which
    # would make the power unusable for the only thing it is ever for.
    target=Target("any", 1),
    keywords=[Keyword.DIVINE],
    group=CHANNEL_DIVINITY,
)
def p1746(c: Cast) -> None:
    """A saving throw, out of turn, with the paladin's presence behind it.

    The bonus is granted as a modifier and then the save is rolled, because
    a save is the one roll the caster cannot ask for directly.
    """
    saves = [e for e in c.world.effects.of(c.target) if e.when is When.SAVE_ENDS]
    if not saves:
        c.note("nothing to save against")
        return
    c.bonus("save", c.cha_mod, until=When.SOTNT)
    c.world.effects.save(c.choose(saves, "which effect do you shake off"))
