"""The mage's own ladder, and the arcanist's last two orb masteries -- the
30 rows that stood between `#642`'s wave and every printed chassis being
complete.

`features/arcanist.py` wrote the mage's eighteen school options (six
Apprentice, six Expert, six Master) and the witch's and sha'ir's rows. It
did not write the **parents** those eighteen hang under, nor the mage's own
spellbook ladder. This file is both.

    f0  the Apprentice school   a pointer: the six options carry `on_leg`
    f4  the Expert school       a pointer
    f6  the Master school       a pointer
    f1  the spellbook           the same mechanic three chassis print
    f2  a power grant
    f7  +3 to five skills       written, not marked
    f8  a short-rest power swap one symbol
    19  "add two of the following powers" and no list -- `defect=`
     2  "two" and "three of the following powers", same shape

## The three school parents are pointers and that is the whole of them

Every one of the eighteen options carries an `on_leg` header for its
school -- `chargen.leg_named_by` reads `enchantment`, `evocation`,
`illusion`, `necromancy`, `nethermancy`, `pyromancy` off each -- and the
mage's legs **are** the six schools. So `chargen.loadout` deals a mage
exactly the three options its leg names and the parents have nothing to
choose: no `chargen.BUILD_OPTIONS` entry, no index arithmetic, no
`c.chosen_option`.

That is the opposite of every fork `#642`'s wave added, and the reason is
worth the line: a choice recorded as a **leg** needs no second axis, and
the mage is the one chassis whose printed fork already was one. The
warlock's pacts are legs too and could not do this, because the hexblade's
and binder's option counts do not align with the seven (`#1264`); the
warpriest's domains are *not* legs and had to become a `BUILD_OPTIONS`
entry read by index.

So three shapes for the same printed sentence across four chassis, each
decided by what the data can support rather than by preference.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Keyword,
    Powers,
    Usage,
    When,
    get,
    power,
)

#: The five skills `-f7` names, in the card's order.
_LORE = ("arcana", "dungeoneering", "history", "nature", "religion")


def _pointer(ref: str, which: str, level: str) -> object:
    """One of the three school parents.

    A pointer and nothing else: the six options below it each carry an
    `on_leg` header for their school, and the mage's legs are the six
    schools, so `loadout` has already dealt the right one. Granting here
    would deal the same card twice, which is `arcanist.py`'s own rule.
    """

    @power(
        ref,
        level=0,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        out_of_combat=True,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "mage_school_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"Choose {which}. You gain the {level} Mage benefit associated '
        'with that school."*\n\n'
        "A **pointer**, and deliberately inert. The six options under this "
        "ref each carry `on_leg` for their school and the mage's legs are "
        "the six schools, so `chargen.loadout` deals the right one without "
        "this row doing anything -- granting here would deal the same card "
        "twice, which is `arcanist.py`'s rule.\n\n"
        "`out_of_combat=True` rather than an empty body with no marker: "
        "the row is complete and a fight has no use for it, and the sweep "
        "credits it as *silent on a board as claimed* instead of reporting "
        "it newly silent."
    )
    return row


mage_school_0 = _pointer(
    "cf:wizard-mage-f0", "a school of magic", "Apprentice")
mage_school_4 = _pointer(
    "cf:wizard-mage-f4",
    "one of the schools for which you have the Apprentice benefit", "Expert")
mage_school_6 = _pointer(
    "cf:wizard-mage-f6",
    "one of the schools for which you have the Expert benefit", "Master")


@power(
    "cf:wizard-mage-f1",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_spellbook(c: Cast) -> None:
    """The spellbook, and preparing out of it.

    The third chassis to print this mechanic -- `cf:wizard-arcanist-f2`
    and `cf:wizard-bladesinger-f3` are the other two -- and written the
    same way for the judgement `controllers_sa.py` records: preparing
    happens after an extended rest, the engine has no rest, so it happens
    when the fight starts, which is the same moment for everything that
    reads it.

    One daily and one utility out of the book into a slot standing empty.
    It does not swap a prepared power for an equivalent one: the slot
    count never changes, so a swap has to prefer one row over another and
    nothing here can.
    """
    book = c.spellbook()
    known = c.world.get(c.me, Powers)
    if not book or known is None:
        return
    for slot in (Usage.DAILY, Usage.ENCOUNTER):
        options = [ref for ref in book
                   if (p := get(ref)) is not None and p.usage is slot]
        prepared = [ref for ref in known.known
                    if (p := get(ref)) is not None
                    and p.usage is slot and p.level > 0]
        if not options or prepared:
            continue
        pick = c.choose(options, f"{c.ref}: which {slot.value} to prepare")
        if pick is not None:
            c.prepare(pick)


@power(
    "cf:wizard-mage-f2",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_ritual(c: Cast) -> None:
    """"You gain the p463 power."

    A no-op grant on the hand a level-1 mage is dealt: `p463` is a level-1
    wizard at-will, so it is inside `loadout`'s pool.
    `cf:wizard-bladesinger-f8` grants the same ref for the same reason.
    """
    c.grant_row("p463", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:wizard-mage-f7",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def mage_lore(c: Cast) -> None:
    """"You gain a +3 bonus to Arcana checks, Dungeoneering checks, History
    checks, Nature checks, and Religion checks."

    **Written rather than marked `narrative=`**, and the five calls are
    why: `c.bonus(f"skill:{name}", ...)` is a real key that
    `chargen.skill_check` reads, and the witch's covens lay exactly this
    for two skills. A row whose clause has a writer is not narrative --
    `content/CLAUDE.md`'s word for that case is *finished*.

    Five calls and not one, because each skill is its own key -- the same
    reason AC and Reflex are two `c.bonus` calls in four other rows of
    this wave.

    Untyped: a class feature stacks with everything and the card prints no
    type word.
    """
    for skill in _LORE:
        c.bonus(f"skill:{skill}", 3, on=c.me, until=When.ENCOUNTER,
                kind="untyped")


@power(
    "cf:wizard-mage-f8",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("turns.short_rest(swap=)",),
)
def mage_recall(c: Cast) -> None:
    """"When you take a short rest, you can replace one unexpended `c9`
    attack power with another from your spellbook of the same level or
    lower."

    A **short** rest, which is the distinction worth marking:
    `cf:wizard-witch-f3` waits on `turns.extended_rest(swap=)` and this
    one is the other rest, so it gets the other symbol rather than
    sharing. The engine has neither, and the two would land separately --
    a short rest happens several times a day and an extended rest once.

    The printed level constraint is the harder half and is named here
    rather than in the symbol: *"the level of the second power must be
    different from that of any unexpended wizard daily attack powers you
    have prepared"* reads the whole prepared set, not just the one being
    swapped.
    """


def _printed_list(ref: str, how_many: str, into_book: bool) -> object:
    """One of the eleven rows whose list was printed and not imported.

    Every one read *"you add two of the following powers to your
    spellbook"* or *"you gain two (or three) of the following powers of
    your choice"* and then listed nothing, so every one carried
    `defect=` -- which **refuses** a row. A mage was therefore refused
    every rung of its ladder at once: no at-will, no cantrip, no daily,
    no utility, at any level. That is not a thin character, it is no
    character.

    The spec lists nothing; the class page lists all eleven, each under
    an ALL-CAPS banner naming a level and a usage. Each feature's
    printed NAME names the same two things, so the pairing is read
    rather than guessed -- the third time in this chassis work that the
    printed name held what the columns did not. `chargen.BUILD_OPTIONS`
    carries the options and `chargen.OPTION_PICKS` how many are taken.
    `#1268`.
    """

    @power(
        ref,
        level=0,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        for took in c.chosen_options(ref):
            c.grant_row(took, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "mage_list_" + ref.rsplit("-f", 1)[-1]
    verb = "add" if into_book else "gain"
    tail = " to your spellbook" if into_book else " of your choice"
    row.__doc__ = (
        f'*"You {verb} {how_many} of the following powers{tail}."*\n\n'
        f"The list is recovered from the printed page -- see "
        f"`_printed_list`. `#1268`."
    )
    return row


def _no_list(ref: str, how_many: str, into_book: bool) -> object:
    """One of the twenty-one rows naming a list the import did not carry."""

    why = (f"the spec reads 'you {'add' if into_book else 'gain'} "
           f"{how_many} of the following powers "
           f"{'to your spellbook' if into_book else 'of your choice'}' and "
           "then lists nothing, so there is no set to choose from")

    @power(
        ref,
        level=0,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "mage_no_list_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


#: **Eleven of the twenty-one have their list back**, and they are the
#: eleven inside the levels this project imports. The ten above them
#: stay `defect=` honestly: the page prints their lists too, but the
#: powers in them are above `MAX_POWER_LEVEL` and so are not in the
#: database to be chosen. That is a different sentence from "the spec
#: lists nothing", and it is the true one for those ten.
for _n in (*range(13, 20),):
    globals()[f"mage_list_{_n}"] = _printed_list(
        f"cf:wizard-mage-f{_n}", "two", True)
for _n in range(20, 30):
    globals()[f"mage_no_list_{_n}"] = _no_list(
        f"cf:wizard-mage-f{_n}", "two", True)
mage_list_9 = _printed_list("cf:wizard-mage-f9", "two", True)
mage_list_10 = _printed_list("cf:wizard-mage-f10", "two", True)
mage_list_11 = _printed_list("cf:wizard-mage-f11", "two", False)
mage_list_12 = _printed_list("cf:wizard-mage-f12", "three", False)


# -- and the arcanist's last two orb masteries ------------------------------


@power(
    "cf:wizard-arcanist-f0c1",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    todo=("c.worsen_save(next_only=)", "c.extend_effect()"),
)
def wizard_orb_imposition(c: Cast) -> None:
    """The orb's second mastery card: a choice of two effects, neither of
    which has a writer.

    *"Designate one creature you have cast a wizard spell upon that has an
    effect that lasts until the subject succeeds on a saving throw. That
    creature takes a penalty to its next saving throw against that effect
    equal to your Wisdom modifier."* -- a penalty to **one named effect's
    next** save, where `c.penalty("save", ...)` is a standing modifier on
    every save the creature makes. Those are different numbers.

    *"Alternatively, extend the duration of an effect created by a wizard
    at-will spell that would otherwise end at the end of your current
    turn."* -- `Effect` has no verb that moves its clock, and
    `c.end_effect` only ends one early.

    Declared with both symbols rather than skipped, because
    `cf:wizard-arcanist-f0s1` grants this ref and a grant of an undeclared
    row is silent in a way nothing reports. `cf:wizard-arcanist-f0c0` and
    `-f0c2` are the two of the four that play.

    **`todo=` and not `dropped=`, and `lint.py` is what said so.** Written
    `dropped=` first, and the gate was exact about why: *"`dropped=` means
    it plays with one clause missing. A row that cannot play is `todo=`,
    which is refused rather than counted ok."* The card prints a choice of
    two effects and neither has a writer, so there is no third clause for
    the row to play -- `todo=` refuses it in play, which is the truth.
    """


@power(
    "cf:wizard-arcanist-f0c3",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def wizard_wand_precision(c: Cast) -> None:
    """The wand's mastery card: *"you gain a bonus to a single attack roll
    equal to your Dexterity modifier."*

    `once=True` is *"a single attack roll"* -- the modifier is spent by
    the first roll that reads it, which is what that keyword is for and
    what `cf:paladin-blackguard-f11s1` uses for the same wording on a
    damage roll.

    The printed *"you must wield your wand"* is the mastery's own
    Requirement and belongs on the row that grants it -- which is where
    `cf:wizard-arcanist-f0s5` puts it, rather than here where it would be
    asked a second time.
    """
    # **No `kind=`, because the card prints no bonus type.** `kind=` is
    # the word the page prints before "bonus" and nothing else, and this
    # card's words are *"a bonus to a single attack roll equal to your
    # Dexterity modifier"*. `kind="power"` was read off the card's TYPE
    # line -- `cf:wizard-arcanist-f0c3 Power`, which says it is a Power,
    # not that its bonus is power-typed. `scripts/bonuses.py` named it.
    # Nothing is lost by the correction: `once=True` already stops a
    # second copy stacking, which is the job the word would have done.
    c.bonus("attack", c.dex_mod, on=c.me, until=When.ENCOUNTER,
            once=True)


def _orb_mastery(ref: str, card: str, wand: bool) -> object:
    """One of the arcanist's two remaining mastery options.

    `cf:wizard-arcanist-f0s0`'s shape exactly -- *"the leg's whole benefit
    is the card beside it, once a fight"*, so the option grants the card
    and adds nothing: *"once per encounter" is the card's own `usage`, and
    a second limit here would be a second budget.*
    """

    @power(
        ref,
        level=0,
        cls="wizard",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "wizard_mastery_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One implement mastery: the `{card}` card, once a fight.\n\n"
        + ("The printed *you must wield your wand* is read here rather "
           "than on the card, which is where the Requirement belongs: the "
           "mastery is granted to a wand-wielder and the card then costs "
           "nothing to check twice."
           if wand else
           "The orb Requirement is the card's own.")
    )
    return row


wizard_mastery_1 = _orb_mastery(
    "cf:wizard-arcanist-f0s1", "cf:wizard-arcanist-f0c1", False)
wizard_mastery_5 = _orb_mastery(
    "cf:wizard-arcanist-f0s5", "cf:wizard-arcanist-f0c3", True)
