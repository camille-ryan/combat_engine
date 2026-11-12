"""The warpriest's ten domain forks -- 104 rows, the biggest single gap
`#642`'s wave leaves behind, and all of it derivable.

`features/warpriest.py` wrote the nine options under `cf:cleric-warpriest-
f1` and deliberately left the **parent** undeclared, on the premise that
*"none of the nine is dealt by the draw -- `chargen.chassis_of("cleric")`
takes the first declared chassis in ref order and that is `templar`, and
nothing in production asks for another"*.

**That premise has gone.** `#1191` made `ORIGINAL` a named option and
`#642` made every printed chassis dealable, so `declared_chassis("cleric")`
now answers `('templar', 'warpriest')` and a dealt warpriest is a
character the game produces. The parent is declared here.

## The domain is one choice and ten forks read it

    f1   the domain itself       9 options, already written
    f0   a Channel Divinity      9 options, each a ref
    f3   an encounter attack     8 options, each a ref
    f6   an encounter attack     9 options, each a ref
    f5   a feature on `p1455`    9 options, each a clause
    f8   a feature on a divine encounter power   9 options, each a clause
    f9   f10   f11   f12         35 options, every one a printed NAME

One `chargen.BUILD_OPTIONS` entry on `-f1` and nine readers of it, which
is the arrangement `features/sentinel.py` and `features/blackguard.py`
record at length.

## And unlike the warlock's pacts, the mapping IS derivable

`#1264` is the warlock's version of this and it could not be written,
because the option counts did not align with the seven pacts. Here they
do, exactly:

    f0 f1 f5 f6 f8 f9 f10 f11   indices 0-8
    f3 f12                      indices 0-7

Nine forks numbered 0-8 and two numbered 0-7 -- so **option index is
domain index**, and the ninth domain simply has no option at `-f3`'s and
`-f12`'s levels. That is a structure and not a guess, which is what lets
all ten forks read `-f1`'s answer by index. Measured before relying on it.

## Where it still stops

`-f9` through `-f12`'s 35 options print a power's **name** with no ref the
importer resolved, so those are `defect=` -- the same shape as the
hexblade's later pact forks, and the same reason. `-f13` through `-f24`
print *"one of the following powers"* and no list.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.warpriest import (
    WORD,
    _on_word_target,
    _on_word_used,
)
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Condition,
    DamageType,
    Keyword,
    When,
    get,
    power,
)
from combat_engine.engine.events import Dropped, PowerUsed, TurnStart
from combat_engine.engine.query import Conditions, bloodied, team

#: The one row the domain is chosen on. Nine other parents read this ref.
DOMAIN = "cf:cleric-warpriest-f1"

#: The nine domains, in index order, which is the order every other fork's
#: options are in -- measured, not assumed. See the module docstring.
DOMAINS = tuple(f"cf:cleric-warpriest-f1s{i}" for i in range(9))


def _domain(c: Cast) -> int:
    """Which domain this warpriest took: 0 to 8.

    One reader, asking about `DOMAIN` whoever is calling -- the
    arrangement `features/blackguard.py::_vice` records. Ten independent
    draws would make a character a different domain in each of its ten
    features and nothing would notice.
    """
    chose = c.chosen_option(DOMAIN) or DOMAINS[0]
    return DOMAINS.index(chose) if chose in DOMAINS else 0


def _fork(ref: str, options: tuple[str, ...], what: str) -> Any:
    """One of the nine parents that read `-f1`'s answer.

    **The index is the domain index**, which the module docstring measures
    rather than assumes. Two forks are short by one -- `-f3` and `-f12`
    stop at index 7 -- so a ninth-domain warpriest gets nothing from those
    two, which is what the compendium prints and not a shortfall here.
    """

    @power(
        ref,
        level=0,
        cls="cleric",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        index = _domain(c)
        if index < len(options):
            c.grant_row(options[index], on=c.me, until=When.ENCOUNTER)

    row.__name__ = "warpriest_fork_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain {what} associated with your domain."*\n\n'
        f"A parent reading `{DOMAIN}`'s answer by index, over "
        f"{len(options)} options."
        + ("\n\n**Short by one, and that is the card.** This fork stops at "
           "index 7 where the domain list runs to 8, so a warpriest of the "
           "ninth domain gets nothing here -- which is what the compendium "
           "prints. Guarded rather than left to raise."
           if len(options) < 9 else "")
    )
    return row


def _grant(ref: str, got: str) -> Any:
    """One of the 29 options or standalone rows that grant a ref."""

    @power(
        ref,
        level=0,
        cls="cleric",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "warpriest_grant_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    declared = get(got)
    level = declared.level if declared is not None else None
    row.__doc__ = (
        f'"You gain the `{got}` power."\n\n'
        + ("A no-op grant: a level-0 cleric row, already dealt. `#1259`."
           if level == 0 else
           "**In the draw**: a level-1 cleric power at a level-1 character "
           "is inside `loadout`'s pool, so whether this grant matters "
           "depends on the hand."
           if level == 1 else
           f"**A real grant.** Level {level} is above a level-1 character, "
           "so the draw cannot reach it."
           if level else
           "The ref does not resolve to a declared row, so the grant is "
           "inert -- recorded here rather than marked, because `grant_row` "
           "on an unknown ref is how every other chassis's forward "
           "references behave.")
    )
    return row


def _defective(ref: str, why: str) -> Any:
    """A row naming something no ref resolves."""

    @power(
        ref,
        level=0,
        cls="cleric",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "warpriest_defect_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f"Refused: {why}"
    return row


# -- the domain parent, which this file is here to declare ------------------


@power(
    DOMAIN,
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_domain(c: Cast) -> None:
    """*"You gain benefits associated with your domain, which include
    special features plus two at-will attack powers."*

    **The parent `features/warpriest.py` left undeclared, and the premise
    for leaving it has gone.** That file reasoned that none of the nine
    options is dealt, because `chassis_of("cleric")` answers `templar` and
    *"nothing in production asks for another"*. `#1191` made `ORIGINAL` a
    named option and `#642` made every printed chassis dealable, so
    `declared_chassis("cleric")` now answers `('templar', 'warpriest')`
    and a dealt warpriest is a character the game produces.

    Declared here rather than in that file so the nine options and the ten
    forks that read them stay together -- and so the commit that changes
    the premise is the commit that records it.

    `arcanist.py`'s rule does not bite: this parent implements no branch
    of its own, it grants the option the domain chose.
    """
    c.grant_row(DOMAINS[_domain(c)], on=c.me, until=When.ENCOUNTER)


# -- the three standalone grants --------------------------------------------


warpriest_grant_2 = _grant("cf:cleric-warpriest-f2", "p1455")
warpriest_grant_4 = _grant("cf:cleric-warpriest-f4", "p12608")
warpriest_grant_7 = _grant("cf:cleric-warpriest-f7", "p12614")


# -- the three forks whose options are refs ---------------------------------


_F0 = tuple(f"cf:cleric-warpriest-f0s{i}" for i in range(9))
_F3 = tuple(f"cf:cleric-warpriest-f3s{i}" for i in range(8))
_F6 = tuple(f"cf:cleric-warpriest-f6s{i}" for i in range(9))

_REFS: dict[str, str] = {
    "cf:cleric-warpriest-f0s0": "p14231",
    "cf:cleric-warpriest-f0s1": "p13943",
    "cf:cleric-warpriest-f0s2": "p16415",
    "cf:cleric-warpriest-f0s3": "p13710",
    "cf:cleric-warpriest-f0s4": "p14245",
    "cf:cleric-warpriest-f0s5": "p14262",
    "cf:cleric-warpriest-f0s6": "p12638",
    "cf:cleric-warpriest-f0s7": "p12651",
    "cf:cleric-warpriest-f0s8": "p14275",
    "cf:cleric-warpriest-f3s0": "p14237",
    "cf:cleric-warpriest-f3s1": "p13944",
    "cf:cleric-warpriest-f3s2": "p16422",
    "cf:cleric-warpriest-f3s3": "p14250",
    "cf:cleric-warpriest-f3s4": "p14263",
    "cf:cleric-warpriest-f3s5": "p12639",
    "cf:cleric-warpriest-f3s6": "p12652",
    "cf:cleric-warpriest-f3s7": "p14276",
    "cf:cleric-warpriest-f6s0": "p14238",
    "cf:cleric-warpriest-f6s1": "p13945",
    "cf:cleric-warpriest-f6s2": "p16423",
    "cf:cleric-warpriest-f6s3": "p13712",
    "cf:cleric-warpriest-f6s4": "p14251",
    "cf:cleric-warpriest-f6s5": "p14264",
    "cf:cleric-warpriest-f6s6": "p12640",
    "cf:cleric-warpriest-f6s7": "p12653",
    "cf:cleric-warpriest-f6s8": "p14277",
}

warpriest_fork_0 = _fork("cf:cleric-warpriest-f0", _F0, "a Channel Divinity")
warpriest_fork_3 = _fork("cf:cleric-warpriest-f3", _F3,
                         "an encounter attack power")
warpriest_fork_6 = _fork("cf:cleric-warpriest-f6", _F6,
                         "an encounter attack power")

for _ref, _got in _REFS.items():
    globals()["warpriest_grant_"
              + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = _grant(_ref, _got)


# -- f5: nine riders on `p1455` ---------------------------------------------


warpriest_fork_5 = _fork(
    "cf:cleric-warpriest-f5",
    tuple(f"cf:cleric-warpriest-f5s{i}" for i in range(9)),
    "a feature")


def _word_rider(ref: str, what: str, *, on_target: bool = True) -> Any:
    """One of `-f5`'s nine riders on `p1455`.

    **Which event each answers is the card's choice**, and
    `features/warpriest.py`'s module docstring settled the reading for the
    nine rows under `-f1`: a rider whose subject is *the target* answers
    `Healed`, because `p1455` picks the creature it heals inside its own
    body and the choice can be declined -- `PowerUsed.targets` names
    whoever was pre-selected and not whoever regained hit points. A rider
    whose subject is the caster or the burst answers `PowerUsed`.

    Seven of these nine are about the target and two about the burst, so
    the two helpers are both used rather than one being picked for
    convenience.
    """

    @power(
        ref,
        level=0,
        cls="cleric",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
    )
    def row(c: Cast) -> None:
        me = c.me
        index = int(ref.rsplit("s", 1)[-1])

        def pay(ev: Any) -> None:
            who = getattr(ev, "target", None) if on_target else me
            if who is None:
                return
            if index == 0:
                c.shift(1, who=who)
            elif index == 2:
                # "Stand up **or** shift 1 square" -- a choice the target
                # makes, so standing is offered only when it is prone and
                # the shift is the other answer.
                #
                # **`Conditions.has` off the world**, which took three
                # tries: there is no `c.prone_now`, no `c.carries`, and
                # `c.carrying` is about the ITEMS a creature holds -- a
                # name that reads like the condition question and answers
                # a different one. `c.prone` is the writer.
                held = c.world.get(who, Conditions)
                if held is not None and held.has(Condition.PRONE):
                    c.cure(Condition.PRONE, on=who)
                else:
                    c.shift(1, who=who)
            elif index == 3:
                amount = c.con_mod
                if amount > 0:
                    c.slide(amount, on=who)
            elif index == 4:
                c.save(on=who)
            elif index == 5:
                amount = c.con_mod
                if amount <= 0:
                    return
                for friend in c.allies():
                    if bloodied(c.world, friend):
                        c.resist(amount, on=friend, until=When.EONT)
            elif index == 6:
                amount = c.con_mod
                if amount <= 0:
                    return
                near = [f for f in c.enemies()
                        if who is not None and c.adjacent_to(who, f)]
                if near:
                    c.flat(amount, dtype=DamageType.THUNDER,
                           on=c.choose(near, f"{c.ref}: which enemy"))
            elif index == 7:
                amount = c.con_mod
                if amount > 0:
                    c.temp_hp(amount, on=who)
            elif index == 8:
                c.teleport(20, who=who, toward=me)

        if on_target:
            _on_word_target(c, pay)
        else:
            _on_word_used(c, pay)

    row.__name__ = "warpriest_word_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One domain's rider on `{WORD}`: {what}.\n\n"
        + ("Answers `Healed`, because its subject is the creature the power "
           "actually healed -- see the helper above."
           if on_target else
           "Answers `PowerUsed`, because its subject is the burst rather "
           "than the one target.")
    )
    return row


warpriest_word_0 = _word_rider(
    "cf:cleric-warpriest-f5s0", "the target shifts 1",
    on_target=True)
warpriest_word_2 = _word_rider(
    "cf:cleric-warpriest-f5s2", "the target stands up or shifts 1")
warpriest_word_3 = _word_rider(
    "cf:cleric-warpriest-f5s3",
    "the target is slid the caster's Constitution modifier")
warpriest_word_4 = _word_rider(
    "cf:cleric-warpriest-f5s4", "the target makes a saving throw")
warpriest_word_5 = _word_rider(
    "cf:cleric-warpriest-f5s5",
    "bloodied allies in the burst resist the caster's Constitution "
    "modifier", on_target=False)
warpriest_word_6 = _word_rider(
    "cf:cleric-warpriest-f5s6",
    "one enemy adjacent to the target takes thunder damage")
warpriest_word_7 = _word_rider(
    "cf:cleric-warpriest-f5s7",
    "the target gains temporary hit points")
warpriest_word_8 = _word_rider(
    "cf:cleric-warpriest-f5s8",
    "the target teleports to a square adjacent to the caster")


@power(
    "cf:cleric-warpriest-f5s1",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("actions.offer_trait(requires=enemy_dropped)",),
)
def warpriest_word_1(c: Cast) -> None:
    """The one of `-f5`'s nine that is not a rider on `p1455` at all.

    *"When an enemy within 5 squares of you drops to 0 hit points, you can
    use `p1455` as an immediate reaction."*

    The **trigger** plays and the offer does not. `Dropped` carries the
    creature and the distance is `c.within`, so "an enemy within 5 drops"
    is answerable -- what cannot be written is putting an existing power
    on the action menu at a differently-priced action for the player to
    choose. `cf:barbarian-berserker-f0`,
    `cf:paladin-blackguard-f3s0` and `cf:paladin-cavalier-f4s0` all wait on
    the same facility.

    The watch is laid anyway, so the day that lands this row is one line:
    everything it needs to know is already in the handler.
    """
    me = c.me

    def dropped(ev: Dropped) -> None:
        victim = getattr(ev, "actor", None)
        if victim is None or team(c.world, victim) is team(c.world, me):
            return
        if victim not in c.within(5, of=me):
            return
        c.note(f"{c.ref}: {WORD} is offered as an immediate reaction")

    c.watch(Dropped, dropped, until=When.ENCOUNTER, on=me, label=c.ref)


# -- f8: nine riders on a divine encounter attack power ---------------------


warpriest_fork_8 = _fork(
    "cf:cleric-warpriest-f8",
    tuple(f"cf:cleric-warpriest-f8s{i}" for i in range(9)),
    "a feature")


def _divine_rider(ref: str, what: str, keyword: Keyword | None,
                  dropped: tuple[str, ...] = ()) -> Any:
    """One of `-f8`'s nine riders on a divine encounter attack power.

    Each gates on the **keyword** of the power used, which is where the
    printed line lives -- *"a divine encounter attack power that has the
    radiant keyword"* -- and `PowerUsed` carries the ref so the keyword is
    a registry lookup. `features/warpriest.py`'s `keywords_of` is the same
    question asked of a resolved row.

    `keyword=None` is the one option that names no keyword (`-f8s8`),
    which is the control for the other eight: if the keyword test ever
    stopped narrowing, that row would behave identically and the rest
    would quietly widen to it.
    """

    @power(
        ref,
        level=0,
        cls="cleric",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.DIVINE],
        dropped=dropped,
    )
    def row(c: Cast) -> None:
        me = c.me
        index = int(ref.rsplit("s", 1)[-1])

        def used(ev: PowerUsed) -> None:
            if getattr(ev, "actor", None) != me:
                return
            rolling = get(getattr(ev, "power", "") or "")
            if rolling is None or rolling.cls != "cleric":
                return
            if not rolling.is_attack or rolling.usage.value != "encounter":
                return
            if keyword is not None and keyword not in rolling.keywords:
                return
            aimed = list(getattr(ev, "targets", ()) or ())
            if index == 0:
                c.teleport(1, who=me)
            elif index == 3 or index == 4 or index == 7:
                for victim in aimed:
                    c.grants_advantage(on=victim, until=When.EONT)
            elif index == 5:
                amount = c.con_mod
                if amount <= 0:
                    return
                for friend in c.allies():
                    if any(c.adjacent_to(v, friend) for v in aimed):
                        c.temp_hp(amount, on=friend)
            elif index == 6:
                c.temp_hp(2 + c.con_mod, on=me)
            elif index == 8:
                for friend in c.within(5, of=me, side="ally"):
                    if friend != me:
                        c.shift(1, who=friend)

        c.watch(PowerUsed, used, until=When.ENCOUNTER, on=me, label=c.ref)

    row.__name__ = "warpriest_divine_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One domain's rider on a divine encounter attack power: {what}.\n\n"
        + (f"Gated on `Keyword.{keyword.name}`, read off the row that was "
           "used."
           if keyword is not None else
           "**No keyword gate**, which is this option's own printed text "
           "and makes it the control for the other eight: if the keyword "
           "test ever stopped narrowing, this row would behave identically "
           "and the rest would quietly widen to it.")
    )
    return row


warpriest_divine_0 = _divine_rider(
    "cf:cleric-warpriest-f8s0", "the warpriest teleports 1",
    Keyword.RADIANT)
warpriest_divine_3 = _divine_rider(
    "cf:cleric-warpriest-f8s3",
    "each target hit grants combat advantage", None,
    dropped=("dsl.Attack.vs(read_at_use)",))
warpriest_divine_4 = _divine_rider(
    "cf:cleric-warpriest-f8s4",
    "each target grants combat advantage", Keyword.PSYCHIC)
warpriest_divine_5 = _divine_rider(
    "cf:cleric-warpriest-f8s5",
    "allies adjacent to a target gain temporary hit points",
    Keyword.RADIANT)
warpriest_divine_6 = _divine_rider(
    "cf:cleric-warpriest-f8s6",
    "the warpriest gains temporary hit points", Keyword.THUNDER)
warpriest_divine_7 = _divine_rider(
    "cf:cleric-warpriest-f8s7",
    "the warpriest has combat advantage against the targets",
    Keyword.RADIANT)
warpriest_divine_8 = _divine_rider(
    "cf:cleric-warpriest-f8s8",
    "each ally within 5 shifts 1", None)


@power(
    "cf:cleric-warpriest-f8s1",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_divine_1(c: Cast) -> None:
    """One domain's feature that answers a turn rather than a power.

    *"At the start of each of your turns, you can use a free action to
    deal necrotic damage to one adjacent bloodied enemy. The necrotic
    damage equals your Constitution modifier."*

    A `TurnStart` watch, not a `PowerUsed` one -- the only option of
    `-f8`'s nine that is not about a power being used, which is why it is
    written out rather than folded into `_divine_rider`.

    *"One adjacent bloodied enemy"* is a choice among those that qualify,
    and a free action costs nothing the engine prices, so none is charged.
    """
    me = c.me

    def at_start(ev: TurnStart) -> None:
        if getattr(ev, "actor", None) != me:
            return
        amount = c.con_mod
        if amount <= 0:
            return
        prey = [f for f in c.enemies()
                if c.adjacent(f) and bloodied(c.world, f)]
        if not prey:
            return
        victim = c.choose(prey, f"{c.ref}: which bloodied enemy",
                          optional=True)
        if victim is not None:
            c.flat(amount, dtype=DamageType.NECROTIC, on=victim)

    c.watch(TurnStart, at_start, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:cleric-warpriest-f8s2",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_divine_2(c: Cast) -> None:
    """One domain's feature, triggered by bloodying or dropping an enemy.

    *"Whenever you use a divine attack power that has the fear keyword to
    bloody an enemy or reduce a non-minion enemy to 0 hit points, you can
    push each enemy within 2 squares of you."*

    Two printed triggers, so two watches -- `Bloodied` and `Dropped`, both
    carrying the creature and the power. Half of an "or" declared looks
    finished and is not.

    *"A divine attack power that has the fear keyword"* is any usage here
    and not the encounter-only narrowing its eight siblings carry, which
    is this card's own wording.
    """
    me = c.me

    def by_fear(ev: Any) -> bool:
        if getattr(ev, "source", None) != me:
            return False
        rolling = get(getattr(ev, "power", "") or "")
        return (rolling is not None and rolling.cls == "cleric"
                and Keyword.FEAR in rolling.keywords)

    def shove(ev: Any) -> None:
        if not by_fear(ev):
            return
        for foe in c.within(2, of=me, side="enemy"):
            c.push(1, on=foe)

    from combat_engine.engine.events import Bloodied

    for event in (Bloodied, Dropped):
        c.watch(event, shove, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the four forks whose options are printed names -------------------------


_NAMED = ("the spec names the granted power by its printed name instead of "
          "a ref, so the importer did not resolve it -- every option of "
          "the four later domain forks is like this and every option of "
          "the three earlier ones resolved")

for _base, _count in ((9, 9), (10, 9), (11, 9), (12, 8)):
    globals()[f"warpriest_fork_{_base}"] = _fork(
        f"cf:cleric-warpriest-f{_base}",
        tuple(f"cf:cleric-warpriest-f{_base}s{i}" for i in range(_count)),
        "an encounter attack power")
    for _i in range(_count):
        _r = f"cf:cleric-warpriest-f{_base}s{_i}"
        globals()["warpriest_defect_"
                  + _r.rsplit("-f", 1)[-1].replace("s", "_")] = _defective(
            _r, _NAMED)


# -- the twelve rows with no list -------------------------------------------


_NO_LIST = ("the spec reads 'you gain one of the following powers of your "
            "choice' and then lists nothing, so there is no set to choose "
            "from")
for _n in (13, 14, 15, 16, 17, 18, 20, 22):
    globals()[f"warpriest_defect_{_n}"] = _defective(
        f"cf:cleric-warpriest-f{_n}", _NO_LIST)
for _n in (19, 21, 23, 24):
    globals()[f"warpriest_defect_{_n}"] = _defective(
        f"cf:cleric-warpriest-f{_n}",
        _NO_LIST + ", and the new power is also meant to replace a daily "
        "the character already has")
