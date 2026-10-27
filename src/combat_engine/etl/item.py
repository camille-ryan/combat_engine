"""Magic items, and the races nothing has ever imported.

An item's page is two things at once. The numbers -- which level each rung
of the ladder appears at, what plus it is, what it costs -- are parsed. The
rules text is not: each Property and each Power comes out as a sanitised
block for somebody to write as code, which is the same split `monster.py`
makes between a stat block and its abilities.

Three decisions are worth knowing before reading any of it.

* **One row per entry, never one per rung.** `build.SCHEMA` argues it at
  length above `CREATE TABLE item`.
* **A family is a family because it prints a ladder table**, not because
  its `Level` has a `+` in it. 1,436 heroic rows have the table against
  1,398 with a plus. The 38 in the gap split two ways: 23 are ladders with
  no enhancement bonus at all -- three levels, three prices, an empty `+`
  column -- and the other 15 are the item sets, whose tables are not
  theirs and are not read here at all.
* **The `Enhancement` column is dead.** It is 0 for all 3,752 rows, so the
  bonus is only ever read off the ladder.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .html import detail, labelled, lead_prose, paragraphs, text
from .sanitise import item_rules, item_spec, scrub

#: The project's scope. Items are gear for characters, so this follows the
#: character ceiling rather than the monster one.
MAX_ITEM_LEVEL = 10

_USAGES = ("at-will", "encounter", "daily", "consumable")
_ACTION = re.compile(
    r"\b(standard|move|minor|free|opportunity|no)\s+action\b"
    r"|\b(immediate\s+(?:interrupt|reaction))\b",
    re.I,
)
#: One rung: level, plus, price. The three cells always come as a triple and
#: the row is two rungs wide, `mic4` being the gap between them -- so reading
#: the cells in document order and ignoring the layout gets every rung,
#: including the paragon and epic ones. A later tier costs nothing to record
#: and the ladder is a fact about the item.
_RUNG = re.compile(
    r'<td class="mic1">(.*?)</td>\s*<td class="mic2">(.*?)</td>'
    r'\s*<td class="mic3">(.*?)</td>',
    re.S,
)
_PRICE = re.compile(r"[\d,]+\s*gp\b", re.I)



#: The line that opens a "choose one of the following" family on a race's page.
_CHOOSE_ONE = re.compile(r"(?i)choose one")

#: A labelled benefit inside a trait block: `<Label> : <benefit>`.
_LABELLED = re.compile(r"(?m)^([A-Z][A-Za-z'\-\s]{2,40}?)\s*:\s*(.+)$")


def sub_option_lines(spec: str, ref: str) -> list[tuple[str, str, str]]:
    """A race's "choose one" family: `(printed label, its ref, its benefit)`.

    Two races print one -- 13 sub-options on one page and 3 on another -- and
    every label was reaching authors verbatim, in the race's own spec and in the
    10 feats and 4 powers that name one. None of the 16 was in
    `localization/names.json`, so `scrub` could not swap them and `leaks.py`
    could not report them: invisible to both halves of the arrangement, which is
    the condition `_other_names` exists to prevent. #277.

    **Identified by the power each one grants, not by a list of headings.** A
    sub-option's benefit always names a card -- that is what the family *is*,
    "each offers particular benefits and provides an associated encounter power"
    -- and the ordinary trait headings printed in the same block never do. So the
    test is structural and this function spells no printed label, which it must
    not: a deny-list of heading names would be the leak it is here to close, the
    same trap `_slot`'s allow-list was written to avoid.

    Numbered by order of appearance, which is deterministic from the page, and
    spelled the way a class feature's legs are (`f0s0`) because it is the same
    idea: sub-option N of one feature.

    **It used to return `{label: ref}` and drop the benefit on the floor**,
    which is why none of the 18 had a `racial_trait` row: the rules text had
    nowhere to go, so the rows were never written and every character of those
    races was short whichever defence bonus and resistance its manifestation
    prints. The caller builds the swap map it still needs from this. #548.
    """
    opens = _CHOOSE_ONE.search(spec)
    if opens is None:
        return []
    out: list[tuple[str, str, str]] = []
    for found in _LABELLED.finditer(spec[opens.start():]):
        label, benefit = found.group(1).strip(), found.group(2)
        # **Either spelling of "a card", because this runs before the
        # cross-reference pass.** At this point in the build a benefit still
        # names its power in words -- `p\d+` does not exist yet and testing for
        # it found nothing at all, which is how the first attempt silently
        # returned no sub-options anywhere. The word survives both stages.
        if not re.search(r"\bp\d+\b|\bpowers?\b", benefit):
            continue
        out.append((label, f"rt:{ref}-s{len(out)}", benefit))
    return out


#: Labels on a race page that are **chassis, not traits**. Every one is already
#: a column or is read into one, and all of them are printed with the same
#: `Label :` shape as a real trait -- which is why the raw count of labelled
#: lines is 591 and the number of traits is 185.
#:
#: `benefits` is the odd one and worth naming: the sub-race layout heads its
#: whole amendment block with it, so it appears on 22 pages and names nothing.
#: These are mechanics words rather than printed names, so writing them down is
#: not a leak -- the same ground `MECHANICAL` stands on.
_CHASSIS = frozenset({
    "average height", "average weight", "ability scores", "size", "speed",
    "vision", "languages", "language", "skill bonuses", "skill bonus", "age",
    "benefits", "benefit",
})


#: A trait line's label, which `_LABELLED` cannot match and must not be widened
#: to: `sub_options` depends on its exact shape.
#:
#: Two things the trait list does that a sub-option never does, each of which
#: cost a trait until the content sweep found it by failing to map:
#:
#: * **a race qualifier in brackets** -- the books write `Forest Walk
#:   (Hamadryad):` where a trait name is shared between races. The bracket is
#:   not part of the name, and the race is already in the ref.
#: * **a digit in the name** -- one trait is `<name> 5:`, the 5 being its range.
#:
#: Found the right way round: content had declared all three and *this reader*
#: was missing them, which is the opposite of what I expected to find and the
#: reason the mapping was checked rather than applied.
_TRAIT_LABEL = re.compile(
    "(?m)^([A-Z][A-Za-z0-9'\u2019\\- ]{2,40}?)\\s*(?:\\([^)]*\\))?\\s*:\\s*(.+)$"
)


def _trait_lines(spec: str, skip: dict[str, str]) -> list[tuple[str, str]]:
    """`[(printed label, its rules text)]` for one race, in page order.

    The traits are already sitting in the race's own block as `Label : text`,
    one per line, which is regular enough to read -- and until #341 that is all
    they were. Nothing held them as rows, so a content author needing to name
    one had to invent an identifier from the label.

    `skip` is the "choose one" family, which `sub_options` has already claimed
    and which nests **under** the trait that offers it rather than sitting
    beside it.

    **A `Benefits:` line belongs to the trait above it, and was being thrown
    away.** A variant race prints each alternate trait as two lines --

        <Trait name>: one sentence of flavour
        Benefits: the mechanics

    -- and `_TRAIT_LABEL` is line-anchored (`(.+)$`), so the trait captured
    its own line and stopped. `Benefits` then matched the label pattern on
    the next line and was dropped as `_CHASSIS` furniture. The result was a
    trait row holding **only the flavour**, which is this module's first
    rule performed backwards.

    It cost nine traits their rules, measured against the compendium, one of
    them a +2 to two ability scores. Latent rather than live -- none of the
    eight races is in `chargen.RACES` -- but a race entering the pool would
    have shipped a character short its printed benefits with nothing to say
    so. #582.

    So a chassis label that is `benefits` is **appended to the previous
    trait** instead of skipped. The other chassis labels are genuinely the
    race's own furniture (size, speed, languages) and still go.
    """
    out: list[tuple[str, str]] = []
    for found in _TRAIT_LABEL.finditer(spec or ""):
        label = " ".join(found.group(1).split())
        rules = found.group(2).strip()
        if label.lower() in ("benefits", "benefit"):
            if out:
                # Joined with a space, so the flavour sentence and the rule
                # read as one line the way the page prints them.
                name, had = out[-1]
                out[-1] = (name, f"{had} {rules}".strip())
            continue
        if label.lower() in _CHASSIS or label in skip:
            continue
        out.append((label, rules))
    return out


#: The one line a race page prints for what it is good at. 44 of 55 carry it
#: and every one of those 44 is this shape -- measured, not assumed.
_SKILL_BONUSES = re.compile(r"^Skill Bonuses?\s*:\s*(.+)$", re.M)

#: `+2 History` inside it. The sign is taken as written: nothing prints a
#: negative one today, and reading `\d+` would turn one into its opposite.
_ONE_BONUS = re.compile(r"([+-]\d+)\s+([A-Za-z]+)")


#: "You have training in Stealth", "You gain training in one skill of your
#: choice", "...one additional skill from your class skills list". Three
#: racial traits print one of these and nothing else does.
_TRAINS = re.compile(r"train(?:ing|ed) in ([^.;]*)", re.I)

#: The one shape whose pool is the character's own class list rather than a
#: named one. `feat.trains_from` holds a printed class and has no way to say
#: this, because on a feat the page always names the class.
_OWN_LIST = re.compile(r"from your class skills?\s*list", re.I)


def _race_training(traits: list[tuple[str, str]]) -> tuple[str, str, str]:
    """`(trains, trains_choice, trains_from)` for one race's trait lines.

    The same three columns `feat.trains*` carries, filled by the same
    argument: granted, chosen-from-a-pool and chosen-from-a-class-list are
    three different sentences, and reading them all as the first trains one
    character in every option a card offers between. #574 measured that on
    the feat side; this is the racial twin. #688.

    Every skill word is checked against `skills.SKILLS` rather than
    trusted, because the clause also contains "one", "additional" and
    whatever the sentence goes on to say.
    """
    from combat_engine.engine.skills import SKILLS

    granted: list[str] = []
    choice = ""
    from_list = ""
    for _label, rules in traits:
        found = _TRAINS.search(rules or "")
        if not found:
            continue
        clause = found.group(1)
        if _OWN_LIST.search(clause):
            # The character supplies the list, so there is no class to
            # record. See `race.trains_from`'s comment for the token.
            from_list = "class"
            continue
        named = sorted({
            w.lower() for w in re.findall(r"[A-Za-z]+", clause)
            if w.lower() in SKILLS
        })
        if named:
            granted.extend(n for n in named if n not in granted)
        else:
            # "one skill of your choice" names nothing, and the pool it
            # means is the whole table. Enumerated rather than tokenised --
            # see the column's comment.
            choice = ",".join(sorted(SKILLS))
    return ",".join(granted), choice, from_list


def _race_skills(spec: str) -> list[tuple[str, int]]:
    """Which skills this race gains a bonus to, and how much. See `race_skill`.

    An empty list means the page prints no such line, which for `r7` is a
    fact about the race and not a failed read -- its skill benefit is a
    *choice*, and `f2900`'s card turns on telling the two apart.

    A word that is not in `skills.SKILLS` is dropped rather than stored, the
    same way `_skills_of` drops one: the line is parsed by shape and that
    shape would match a sentence which prints anything else the same way.
    """
    from combat_engine.engine.skills import SKILLS

    found = _SKILL_BONUSES.search(spec or "")
    if not found:
        return []
    out: list[tuple[str, int]] = []
    for amount, word in _ONE_BONUS.findall(found.group(1)):
        skill = word.lower()
        if skill in SKILLS and skill not in {s for s, _ in out}:
            out.append((skill, int(amount)))
    return out


def races(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Any,
    names: dict[str, dict[str, str]],
) -> None:
    """Every printed race. Nothing here gates on tier -- a race has none.

    Two layouts. The 46 full races print their traits in a blockquote under
    a `RACIAL TRAITS` heading; the 9 sub-races are an essay whose mechanics
    are the last `<h3>` section, amending the parent race rather than
    restating it. Everything from the first racial power card onwards is
    dropped: those powers are already rows in `power`, because the
    compendium files them under the race in their Class column.
    """
    for row in source.execute("SELECT ID, Name, Size, Txt FROM Race ORDER BY ID"):
        ref = f"r{row['ID']}"
        name = (row["Name"] or "").strip()
        body = _own_page(detail(row["Txt"] or ""))

        # Nine sub-race rows leave the column blank and print the size in
        # their traits instead; the rest agree with the column.
        size = (row["Size"] or "").strip().lower()
        if not size:
            found = re.search(r"<b>\s*Size\s*</b>\s*:?\s*([A-Za-z]+)", body)
            size = found.group(1).lower() if found else ""

        traits = re.search(r"<blockquote>(.*?)</blockquote>", body, re.S)
        spec = text(traits.group(1)) if traits else text(
            re.split(r"<h3[^>]*>.*?</h3>", body, flags=re.S)[-1]
        )
        spec = re.split(r"\s*Published in\b", spec)[0].strip()

        # Both shapes: `<i>` on the 46 full pages, a bare text node on the 9
        # sub-races. Reading only the first left those 9 empty. #352.
        flavour = lead_prose(body)
        # **The "choose one" family gets refs of its own.** Swapped here as well
        # as the race's own name, so the spec an author reads says `rt:r33-s0`
        # where it said a printed label -- and registered in `names` so the other
        # tables that name one can be swapped too, and so `leaks.py` can finally
        # see them.
        option_lines = sub_option_lines(spec, ref)
        # `_trait_lines` wants the family's **labels** only -- to skip them,
        # since a sub-option nests under the trait that offers it rather than
        # sitting beside it -- and the ref each label maps to is not settled
        # until `granted` below can say whether it is already a power.
        option_labels = {label: o_ref for label, o_ref, _r in option_lines}
        # **Each printed trait becomes a row of its own.** They were prose and
        # only prose, so content needing to name one invented a ref out of the
        # printed label -- 94 of them in tracked source, each with nothing a
        # checker could compare it against. #341.
        traits = _trait_lines(spec, option_labels)
        # **A trait that is already a power keeps the power's ref.** 42 of the
        # 185 are printed twice: once as a line in the traits list and once as a
        # whole card, which the compendium files under the race in its Class
        # column -- so `power` already holds the firing row. Minting an `rt:`
        # ref for those would be one thing with two identities, which is the
        # fault this repo keeps finding, and it showed up immediately as 23
        # specs that stopped resolving a power because the new ref won first.
        granted = {
            (names.get(p_ref) or {}).get("name", ""): p_ref
            for (p_ref,) in out.execute(
                "SELECT ref FROM power WHERE class = ?", (ref,)
            )
        }
        granted.pop("", None)
        # **A sub-option that is already a power keeps the power's ref**, the
        # same rule the trait loop below applies and for the same reason.
        # One race's two "sub-options" are its two racial powers and nothing
        # else -- "You have the <card> power" -- so the label *is* the
        # power's printed name. Minting an `rt:` ref for those made one thing
        # with two identities, and it showed immediately: the early scrub
        # swapped the power's name for the sub-option's own ref, so the row
        # read "You have the rt:r1-s0 power" and named itself instead of its
        # card. #528's fault in a new place.
        #
        # The surviving rows are the ones that carry something besides a
        # card: thirteen manifestations with defence bonuses, resistances
        # and breathing underwater, which is the gap #548 is about.
        options = {
            label: granted.get(label, o_ref)
            for label, o_ref, _rules in option_lines
        }
        option_lines = [
            (label, o_ref, rules)
            for label, o_ref, rules in option_lines
            if label not in granted
        ]
        trait_refs: dict[str, str] = {}
        rows: list[tuple[str, int, str, str]] = []
        for i, (label, rules) in enumerate(traits):
            if label in granted:
                trait_refs[label] = granted[label]
                continue
            trait_ref = f"rt:{ref}-t{i}"
            trait_refs[label] = trait_ref
            rows.append((trait_ref, i, label, rules))
        for trait_ref, i, label, rules in rows:
            out.execute(
                "INSERT OR REPLACE INTO racial_trait VALUES (?,?,?,?)",
                (trait_ref, ref, i,
                 scrub(rules, {name: ref, **trait_refs, **options})),
            )
            # The label where every other printed name lives, and the rules text
            # beside it -- taken before the scrub, so the two are one extraction.
            names[trait_ref] = {"name": label, "rules_text": rules}
        trains, trains_choice, trains_from = _race_training(traits)
        out.execute(
            "INSERT INTO race VALUES (?,?,?,?,?,?,?,?)",
            (ref, row["ID"], size, json.dumps(_scores(spec)),
             scrub(spec, {name: ref, **trait_refs, **options}),
             trains, trains_choice, trains_from),
        )
        # **Off the unscrubbed spec**, which is where the line still reads
        # "+2 History" rather than a ref. Nothing in it is a printed name --
        # see `race_skill`'s own comment -- so the two extractions do not
        # have to agree about scrubbing, only about the text. #694.
        out.executemany(
            "INSERT INTO race_skill VALUES (?,?,?)",
            [(ref, skill, bonus) for skill, bonus in _race_skills(spec)],
        )
        names[ref] = {"name": name, "description": flavour}
        # **A sub-option gets a row, not only a name.** Its label was
        # registered here and its *benefit* was dropped on the floor, so all
        # 18 were refs with nothing behind them -- cited in this race's own
        # spec and in the feats and powers that name one, resolving to
        # nothing, and no instrument watching: `refs.py` skips `rt:` as a
        # placeholder and never reads a spec anyway. A character of these
        # races is short whichever defence and resistance its manifestation
        # prints. #548.
        #
        # `ord` continues past the plain traits rather than restarting, so
        # the two families order against each other the way the page does.
        # The ref itself carries the choice number, which is what
        # `chargen.RaceLine.manifestations` sorts on.
        #
        # **These are alternatives, not additions**, and the thing that
        # keeps them apart lives in chargen: `traits` excludes a `-s` ref
        # and `granted` adds back exactly one, paired with the power the
        # sub-option names. Writing these rows without that guard hands one
        # race's character all thirteen at once.
        for n, (label, option_ref, rules) in enumerate(option_lines):
            out.execute(
                "INSERT OR REPLACE INTO racial_trait VALUES (?,?,?,?)",
                (option_ref, ref, len(rows) + n,
                 scrub(rules, {name: ref, **trait_refs, **options})),
            )
            names[option_ref] = {"name": label, "rules_text": rules}
        report.races += 1
        report.racial_traits += len(rows) + len(option_lines)
        report.traits_are_powers += len(traits) - len(rows)


#: "+2 Charisma, +2 Constitution or +2 Strength". 46 of the 55 races print
#: one; the rest are sub-races that amend a parent and say nothing.
_SCORES = re.compile(r"Ability scores\s*:\s*([^\n]+)", re.I)
_BUMP = re.compile(r"\+(\d+)\s+([A-Za-z]+)")


def _scores(spec: str) -> dict[str, int]:
    """What a race adds to your ability scores, as an engine ability key.

    The "or" in "+2 Constitution, +2 Strength or +2 Wisdom" is a choice
    the character makes, and this keeps all three -- which of them is
    taken belongs to `chargen`, not to a parser. A race that prints
    nothing gets an empty dict rather than a guess.
    """
    found = _SCORES.search(spec or "")
    if not found:
        return {}
    out: dict[str, int] = {}
    for amount, ability in _BUMP.findall(found.group(1)):
        key = ability[:3].lower()
        if key in ("str", "con", "dex", "int", "wis", "cha"):
            out[key] = int(amount)
    return out


def items(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Any,
    names: dict[str, dict[str, str]],
) -> None:
    """Heroic magic items, their ladders and their blocks -- **and gear**.

    **`Category = 'Equipment'` is the adventuring gear and it has no
    level**, so the heroic band alone excluded all 233 of it -- `i390`,
    `i251`, `i332` and the rest of the ordinary kit. Four rows print a
    Requirement naming one: `p16442`, `p16443` and `p16444` want `i390`
    and `p15845` an instrument, and none of them had a ref to name. #876.

    **This docstring is itself the rule's own worked example.** The first
    draft of it spelled two of those names out, and the gate this import
    enables reported it immediately -- `etl/item.py:469` and `:471`,
    alongside the content sites. A name must not enter a tracked file and
    an explanation is not an exemption; refs do the job here exactly as
    well.

    It is the **same table**, not the separate section #876 supposed:
    every one of the 233 carries `LevelSort = 0`, which is the only reason
    `BETWEEN 1 AND` dropped them. `IsMundane` is 0 across the whole table
    and tells nothing.

    **Chargen will not deal a crowbar**, which was checked before this
    landed rather than hoped: its item query joins `item_step`, and gear
    has no steps -- `_head` reads no level price off a page costing
    "40 gp", so `steps` comes out empty and the join excludes the row.

    **And this makes four existing name leaks visible rather than making
    any.** Of the 233 names, only 4 both `identifies` and already appear in
    a tracked file, and all four are the printed Requirement text of the
    rows above. `leaks.py` cannot report a name it does not hold, so those
    four have been in the tree unseen; with a ref to name, they can be
    written as refs. The other 229 are waived or absent.
    """
    scores: list[float] = []
    for row in source.execute(
        "SELECT ID, Name, Category, Rarity, LevelSort, Source, Txt FROM Item "
        "WHERE (LevelSort BETWEEN 1 AND ?) OR Category = 'Equipment' "
        "ORDER BY ID",
        (MAX_ITEM_LEVEL,),
    ):
        scores.append(_one_item(dict(row), out, report, names))
    report.scores["item"] = sum(scores) / max(1, len(scores))


def _one_item(
    row: dict,
    out: sqlite3.Connection,
    report: Any,
    names: dict[str, dict[str, str]],
) -> float:
    ref = f"i{row['ID']}"
    name = (row["Name"] or "").strip()
    category = (row["Category"] or "").strip()
    body = _own_page(detail(row["Txt"] or ""))

    # Everything before the first `<h2>` belongs to the item itself; after
    # it, every line belongs to a block and is that block's to record.
    head = body.split("<h2")[0]
    slot, base, price, enh_to, crit = _head(head)
    scaling = 'class="magicitem"' in body
    steps = _ladder(body) or ([] if price is None else [(row["LevelSort"], 0, price)])
    blocks = [] if category == "Item Set" else _blocks(body)
    if category == "Item Set":
        # A set page embeds its members' **whole pages** as further `<h1>`
        # cards, and every one of those members is already its own `Item`
        # row -- so parsing past the first heading would author all four of
        # them a second time under an id that is not theirs. What is left
        # is the set's own benefit table, which exists nowhere else.
        report.sets_skipped += 1
        spec = scrub(_set_benefits(body), {name: ref})
    else:
        spec = item_spec(head, ref, name)

    score = _score(spec or blocks or enh_to or crit, base or slot, steps)
    out.execute(
        "INSERT INTO item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ref, row["ID"], category, slot, (row["Rarity"] or "").strip(),
            row["LevelSort"], int(scaling),
            json.dumps(base), enh_to, crit,
            json.dumps([b.strip() for b in (row["Source"] or "").split(",") if b.strip()]),
            spec, score,
        ),
    )
    names[ref] = {"name": name, "description": _description(body)}
    report.items += 1

    for level, plus, cost in steps:
        out.execute(
            "INSERT OR IGNORE INTO item_step VALUES (?,?,?,?)",
            (ref, level, plus, cost),
        )
        report.item_steps += 1

    powers = properties = 0
    for idx, (kind, usage, action, keywords, head, fragment) in enumerate(blocks, 1):
        if kind == "power":
            powers += 1
            block_ref = f"{ref}p{powers}"
        else:
            properties += 1
            block_ref = f"{ref}x{properties}"
        out.execute(
            "INSERT INTO item_block VALUES (?,?,?,?,?,?,?,?)",
            (
                block_ref, ref, idx, kind, usage, action,
                # The name a block prints is the **item's**, so it is swapped
                # for the item's ref and not the block's -- "stowed in the
                # <name>" means the whole item, and pointing it at the
                # paragraph that happens to say it reads as nonsense.
                json.dumps(list(keywords)), item_spec(fragment, ref, name),
            ),
        )
        # **An entry for every block, named only when the page names one.** A
        # block is a Power or a Property *inside* an item and the compendium
        # usually gives it no name of its own -- 6 of 2,491 have one -- so this
        # wrote nothing at all for the rest. It still carries printed rules,
        # which is what an item's card shows, so the entry exists either way.
        # #349.
        entry: dict[str, str] = {"rules_text": item_rules(fragment)}
        if head:
            entry["name"] = head
        names[block_ref] = entry
        report.item_blocks += 1

    return score


def _own_page(body: str) -> str:
    """Everything up to the second `<h1>`, which is never this row's.

    On the 15 item sets the later headings are the members' own pages, and
    each member is a separate `Item` row. On another 12 they are the stat
    block of a creature the item conjures, printed inline. Neither belongs
    to the entry being parsed, and both would otherwise be authored twice.
    """
    cuts = [m.start() for m in re.finditer(r"<h1\b", body)]
    return body[: cuts[1]] if len(cuts) > 1 else body


def _description(body: str) -> str:
    found = re.search(r'<p class="miflavor">(.*?)</p>', body, re.S)
    if found is None:
        # A set page opens with an unclassed paragraph instead.
        found = re.search(r"<p>(.*?)</p>", body, re.S)
    return text(found.group(1)) if found else ""


def _ladder(body: str) -> list[tuple[int, int, int]]:
    table = re.search(r'<table class="magicitem">(.*?)</table>', body, re.S)
    if table is None:
        return []
    rungs: dict[int, tuple[int, int, int]] = {}
    for lvl, plus, cost in _RUNG.findall(table.group(1)):
        level = _digits(text(lvl))
        rungs.setdefault(level, (level, _digits(text(plus)), _digits(text(cost))))
    return [rungs[k] for k in sorted(rungs)]


def _digits(cell: str) -> int:
    found = re.sub(r"[^\d]", "", cell)
    return int(found) if found else 0


def _head(head: str) -> tuple[str, list[str], int | None, str, str]:
    """The slot, the base-item restriction, the price, and the bonus lines.

    **The base line is the first labelled line, whatever it is called.** The
    books head it `Weapon`, `Neck Slot`, `Wondrous Item`, a reward title
    (`f1087`) and 28 other ways, so matching by label means keeping a list of 32 phrases
    -- one of which is also the printed name of an item, and would therefore
    be a leak the moment it was written down. Position is exact: all 1,862
    non-set heroic pages put it first.

    An item with no ladder prints its one price on that line and nowhere
    else, so it is read here rather than left at zero; otherwise a quarter
    of the heroic tier is invisible to a treasure-by-level query. `None`
    means the line named no price at all, which is not the same as the six
    assassin poisons that are printed **at 0 gp** and do have a rung.
    """
    slot, base, price, enh_to, crit = "", [], None, "", ""
    first = True
    for cls, para in paragraphs(head):
        if "mistat" not in cls:
            continue
        pair = labelled(para, ("b", "i"))
        if pair is None:
            continue
        label, value = pair[0].strip(), pair[1].strip()
        if first:
            first = False
            slot, base = _slot(label), _base(value)
            found = _PRICE.search(value)
            price = _digits(found.group()) if found else None
        elif label.lower() == "enhancement bonus":
            enh_to = _enh_to(value)
        elif label.lower() == "critical":
            crit = value
    return slot, base, price, enh_to, crit


#: Every word `item.slot` may hold. An **allow-list, and that is the point**:
#: the 32 phrases the base line is headed with are printed titles, and 15 of
#: them name a reward category rather than a place on a body -- one of those
#: 15 is also the printed name of a feat, which is how `leaks.py --specs`
#: found this. A deny-list would mean writing those 15 titles into tracked
#: source, which is the leak the docstrings here and in `sanitise.py` were
#: right to refuse. So the vocabulary is written instead. Every word below
#: already appears in tracked source -- as an `items/` module name, as a
#: `slot=` argument, or in `equipment.py`'s two comparisons -- because it is
#: game vocabulary, not a name.
_SLOTS = frozenset(
    {
        "alchemical",
        "ammunition",
        "armor",
        "arms",
        "companion",
        "consumable",
        "familiar",
        "feet",
        "hands",
        "head",
        "implement",
        "mount",
        "neck",
        "ring",
        "waist",
        "weapon",
        "wondrous",
    }
)


def _slot(label: str) -> str:
    """The place this goes, or `""` for a reward that goes nowhere.

    A boon occupies no slot, so `""` is the true answer and not a loss.
    `equipment.py` keys `gear.worn` by `slot or ref`, which means the
    empty string lets a character hold **any number** of distinct rewards;
    echoing the printed category made every reward of a kind overwrite the
    last one, so 27 divine boons shared a single key.
    """
    low = " ".join(label.lower().split())
    for tail in (" slot", " item"):
        if low.endswith(tail):
            low = low[: -len(tail)]
            break
    return low if low in _SLOTS else ""


def _base(value: str) -> list[str]:
    """What the item may be laid on top of, as the page names it.

    This is load-bearing: a magic weapon is a longsword with properties and
    not a new weapon group, so the row has to say which existing weapons it
    takes. The line also carries the price when the item has no ladder, and
    sometimes a parenthetical about how it is fitted; neither is a weapon.
    """
    value = _PRICE.sub(" ", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    parts = re.split(r",|\bor\b", value, flags=re.I)
    return [p for p in (" ".join(x.split()).lower() for x in parts) if p]


def _enh_to(value: str) -> str:
    low = value.lower()
    if "attack" in low:
        return "attack_damage"
    if "defen" in low or "fortitude" in low:
        return "defences"
    return "ac" if re.search(r"\bac\b", low) else ""


def _blocks(body: str) -> list[tuple[str, str, str, tuple[str, ...], str, str]]:
    """Every `<h2>` and the paragraphs under it: the unit of work."""
    heads = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", body, re.S))
    out = []
    for n, head in enumerate(heads):
        stop = heads[n + 1].start() if n + 1 < len(heads) else len(body)
        out.append((*_block_head(text(head.group(1))), body[head.end(): stop]))
    return out


def _block_head(heading: str) -> tuple[str, str, str, tuple[str, ...], str]:
    """The kind, usage, action, keywords and any name, off one `<h2>`.

    Nothing here reads position, because the page does not keep one: the
    diamond separator sits after `Attack Power` on most pages and before it
    on 40 others. A parenthesised group is the action if it says so and
    keywords otherwise, and the usage is whichever of the four words is
    left outside the brackets.
    """
    act = _ACTION.search(heading)
    action = re.sub(r"\s+", " ", (act.group(1) or act.group(2)).lower()) if act else ""
    keywords: list[str] = []
    for group in re.findall(r"\(([^)]*)\)", heading):
        if _ACTION.search(group):
            continue
        keywords += [w.strip().lower() for w in group.split(",") if w.strip()]

    rest = re.sub(r"\([^)]*\)", " ", heading)
    kind = "property" if re.fullmatch(r"\s*propert(?:y|ies)\s*", rest, re.I) else "power"
    usage = next((u for u in _USAGES if re.search(rf"\b{u}\b", rest, re.I)), "")
    # Whatever survives having all four columns struck out is a printed
    # name, and almost nothing does -- an item's blocks are headed `Power`
    # and `Property`, not called anything. A residue with a digit in it is
    # a charge limit ("5 Charges/Day"), not a name.
    name = re.sub(
        r"\b(attack|utility|power|propert(?:y|ies)|at-will|encounter|daily"
        r"|consumable|immediate|interrupt|reaction|standard|move|minor|free"
        r"|opportunity|no|action)\b",
        " ",
        rest,
        flags=re.I,
    )
    name = " ".join(name.split()).strip(" ,;/")
    if re.search(r"\d", name) or len(name) < 4:
        name = ""
    return kind, usage, action, tuple(keywords), name


def _set_benefits(body: str) -> str:
    """A set's own rules: what you get for wearing two pieces, or four.

    The other table on the page lists the members by name, which is the one
    thing that must not be copied out -- and does not need to be, since each
    member is already a row of its own.
    """
    for table in re.findall(r"<table[^>]*>(.*?)</table>", body, re.S):
        if "Pieces" not in table:
            continue
        lines = []
        for tr in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            cells = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) == 2:
                lines.append(f"Pieces {cells[0]}: {cells[1]}")
        return "\n".join(lines)
    return ""


def _score(described: Any, placed: Any, steps: list) -> float:
    """Whether the three things a row is for came out of the page.

    Something the item does, somewhere to put it, and a price. `described`
    counts the two bonus columns as well as the text, because a plain `+1
    weapon` has no Property and no Power and is not thereby half-parsed --
    its whole rule is the enhancement bonus and the critical line, and both
    are already columns.
    """
    checks = [bool(described), bool(placed), bool(steps)]
    return sum(checks) / len(checks)
