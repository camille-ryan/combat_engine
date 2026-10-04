"""Feats, and the prerequisite problem.

Every tier, not just heroic. `tier` is the printed column and nothing more,
because 664 rows print no tier line at all -- not in `Txt` either -- and a
guess would be indistinguishable from a reading. `min_level` comes off the
prerequisite instead, so "is this a heroic feat" stays a query somebody can
revisit:

    WHERE tier = 'Heroic' OR (tier = '' AND min_level <= 10)

**The prerequisite is the whole of the difficulty.** It names classes,
races, powers, class features, deities and skills in the publisher's prose,
so it can be stored neither raw nor scrubbed: `sanitise.scrub` only swaps
strings it has a name table for, and there is no name table for a deity or
for "you have a spellscar". A scrubbed raw column would therefore have
shipped those sentences verbatim into a spec an authoring agent reads.

So it is a JSON expression tree of atoms, each of which is an id, a number
or a word the engine already says out loud -- and the connective is kept,
because "Fighter or Warlord" and "Fighter, Dex 13" are different gates:

    {"all": [{"any": [{"class": "fighter"}, {"class": "warlord"}]},
             {"ability": "dex", "min": 13}]}

What will not reduce to an atom becomes `{"term": "q17"}`, and `unparsed`
counts those rather than keeping their text. An author sees `unparsed: 2`
and knows the gate is incomplete without learning a word of it; the
readable text goes to `localization/names.json`, which is gitignored.
Term ids are handed out over a **global** sorted dictionary of clause
texts, so "must worship <deity>" is one term shared by its ten feats --
answer it once and all ten are answered -- and the ids do not move between
rebuilds.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from .html import detail, paragraphs, text
from .sanitise import (
    RULES_TERMS,
    description,
    mechanical,
    power_rules,
    power_spec,
    scrub,
)

#: A whole power card printed inside a feat's entry. 227 feats carry one,
#: and it is the power dialect exactly -- verified on feat 595 -- so
#: `sanitise.power_spec` reads the fragment unchanged.
_CARD = re.compile(r'<h1[^>]*class="[a-z-]*power"', re.I)
_HEAD = re.compile(r"<h1\b")

#: The three lines that are not the Benefit. The tier is its own column,
#: the prerequisite is the tree, and the footer is about the page.
_FURNITURE = re.compile(
    r"^(?:(?:heroic|paragon|epic)\s+tier$|prerequisite\b|published in\b)", re.I
)

#: The compendium's own errata apparatus, which is about a *previous
#: printing* of the paragraph above it rather than about the feat.
#: `power_spec` already drops `Update`; the feat pages use five more
#: words for the same thing.
#:
#: Unlike the furniture above, a match here takes **the rest of its
#: paragraph** with it. Dropping only the heading leaves the instruction
#: behind, and an author reads a note about editing a sentence as though
#: it were a rule.
_ERRATA = re.compile(
    r"^(?:update|updated|addition|errata|change|correction)\b", re.I
)

#: **Where the errata block ends.** Taking the rest of the paragraph is
#: right for the instruction the heading introduces and wrong for what
#: comes after it: on 13 pages the `Update (<date>)` block sits *between*
#: the Benefit and the `Associated Powers:` line, in the same run of
#: loose `<br/>`-separated text, so the list went down with the erratum
#: and those feats' associated set was unknowable for no reason but the
#: order the page prints in. This line is the page's own section heading,
#: not part of an edit to a previous printing, so it ends the block.
_RESUMES = re.compile(r"^Associated Powers\s*:", re.I)

#: `href="power.php?id=NNNN"` on an Associated Powers member. `build._HREF` is
#: the same pattern; it cannot be imported, because `build` imports this module.
_LINKED = re.compile(r'href="power\.php\?id=(\d+)"')


def _above_ceiling(source: sqlite3.Connection, txt: str) -> dict[str, str]:
    """Printed name -> ref, for each linked member this build will not import.

    **The leak `_members` could not close.** A member whose clause the page
    writes *bare* runs straight into the next member's name with no separator,
    and `_members`' un-gluing only fires on the parenthesised spelling -- so for
    `f2712` the brief ended "... used as a ranged attack <name>", a printed
    power name shown to an author, which is the one thing this project may not
    do. #232.

    Neither of the two obvious fixes reaches it. A heuristic split on title case
    is wrong on every clause that ends in a proper noun. A lookup in `by_name`
    cannot find it either, and that is the whole difficulty: the glued member is
    **above the level ceiling**, so it was never imported, has no `names.json`
    entry, and `leaks.py --specs` cannot see it by construction.

    The page links every member by id, including the ones above the ceiling, so
    the ids are exact where the names are not. So the name is replaced by the ref
    it would have had, rather than deleted: paragon and epic are meant to be
    imported eventually, and on the day they are, `p4450` is already the right
    row and this feat already points at it. A deleted name would have had to be
    found again.

    Until then the ref resolves to nothing, which is honest -- it says *which*
    power without saying what it is called, the same trade the rest of this
    component makes.
    """
    from .build import MAX_POWER_LEVEL

    out: dict[str, str] = {}
    for found in _LINKED.findall(txt or ""):
        row = source.execute(
            "SELECT Name, Level FROM Power WHERE ID = ?", (int(found),)
        ).fetchone()
        if row and (row["Level"] or 0) > MAX_POWER_LEVEL and (row["Name"] or "").strip():
            out[row["Name"].strip()] = f"p{int(found)}"
    return out

#: The long forms the pages also print. The short ones come off the enum.
_SPELT_OUT = {
    "strength": "str", "dexterity": "dex", "constitution": "con",
    "intelligence": "int", "wisdom": "wis", "charisma": "cha",
}  # fmt: skip


@lru_cache(maxsize=1)
def _vocabulary() -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    """The three engine tables an atom is checked against.

    Imported here rather than at the top, as `sanitise` does: importing
    `combat_engine.engine.skills` pulls in the whole rules kernel, and the
    ETL has no other reason to load it. `Ability`, `Keyword` and `SKILLS`
    are the reason those three atom kinds are safe to write down at all, so
    they are read off the engine rather than copied.
    """
    from combat_engine.engine.skills import SKILLS
    from combat_engine.engine.types import Ability, Keyword

    abilities = {a.value: a.value for a in Ability} | _SPELT_OUT
    sources = frozenset(
        k.value
        for k in (
            Keyword.MARTIAL, Keyword.ARCANE, Keyword.DIVINE, Keyword.PRIMAL,
            Keyword.PSIONIC, Keyword.SHADOW, Keyword.ELEMENTAL,
        )
    )  # fmt: skip
    return abilities, sources, frozenset(SKILLS)


#: How an opaque clause is labelled in `prereq_term`. The kind is the only
#: thing about it that can be said in the open, and it is enough to sort the
#: work: every `deity` is the same missing feature.
#: A race sub-option's ref, as `item.sub_options` mints them.
_SUB_OPTION = re.compile(r"rt:r\d+-s\d+")

_KINDS = (
    (r"^(?:you\s+)?must\s+(?:not\s+)?worship", "deity"),
    (r"\b(?:regional\s+)?(?:background|benefit)$", "background"),
    (r"\btheme$", "theme"),
    (r"\bheritage$", "heritage"),
    (r"\brole$", "role"),
    (r"\bracial\s+(?:trait|feature|power)$", "racial"),
    (r"\bmulticlass|\bmulticlassing\b", "multiclass"),
    (r"\bpower$", "power"),
    (r"\bfeature$", "feature"),
    (r"\bfeat\.?$", "feat"),
    (r"\britual", "ritual"),
    (r"^proficien|^train", "proficiency"),
    (r"alignment$|^good$|^evil$", "alignment"),
    (r"\bsize$|^small$|^medium$", "size"),
    (r"\bmanifestation$|\bpact$", "class option"),
)


def _trimmed(source: sqlite3.Connection, row: Any, spec: str) -> str:
    """A benefit with each above-ceiling member's name swapped for its ref.

    Longest first, so a name that contains another is swapped whole.
    """
    found = _above_ceiling(source, row["Txt"] or "")
    for name in sorted(found, key=len, reverse=True):
        spec = re.sub(re.escape(name), found[name], spec)
    return spec


def feats(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Any,
    names: dict[str, dict[str, str]],
) -> None:
    """Every feat, its prerequisite tree, and any power card it prints.

    Two passes, because the term dictionary is global: the first parses
    every prerequisite and leaves each opaque clause holding its own text,
    the second sorts those texts, numbers them `q0...qN` and substitutes.
    Numbering per feat would have been one pass and would have given the
    same sentence a different id in each of the ten feats that print it,
    which is the one thing the table exists to prevent.
    """
    rows = list(
        source.execute("SELECT ID, Name, Tier, Source, Txt FROM Feat ORDER BY ID")
    )
    index = _Index(source, out, names, rows)

    uses: Counter[str] = Counter()
    trees: dict[int, dict | None] = {}
    for row in rows:
        clause = _prerequisite(row["Txt"] or "")
        tree = _tree(clause, index) if clause else None
        trees[row["ID"]] = tree if _count(tree) else None
        uses.update(_opaque(tree))

    ordinary = mechanical() | {w for (w,) in out.execute("SELECT word FROM common_word")}
    terms = {clause: f"q{n}" for n, clause in enumerate(sorted(uses))}
    # **A clause naming a race's "choose one" option resolves to that option**,
    # which is #277's title: it could not, so each such prerequisite minted an
    # opaque `qN` pointing at nothing -- 11 of them, every one used exactly once.
    # `item.races` has already run by here, so `names` holds the 18 sub-option
    # refs and the match is a lookup rather than a parse.
    #
    # The `qN` numbering is left alone and the resolved ones overwritten on top,
    # rather than numbering around them. Renumbering would shift every opaque ref
    # after the first match and rewrite the prereq tree of every feat in the
    # corpus -- a deterministic diff, but an enormous one for no gain.
    options = {
        row["name"].lower(): ref
        for ref, row in names.items()
        if _SUB_OPTION.fullmatch(ref) and row.get("name")
    }
    for clause in list(terms):
        low = clause.lower()
        found = next((r for label, r in options.items() if label in low), None)
        if found is not None:
            terms[clause] = found
    # **Merged by ref, because two clauses can name one sub-option.** A `qN` is
    # unique by construction and these used to be inserted one per clause; a
    # resolved ref is not, and the printed prerequisites say the same option two
    # ways -- which hit `prereq_term`'s primary key and took the whole build down.
    # The uses add up, which is what `uses` means.
    merged: dict[str, tuple[str, int]] = {}
    for clause, ref in terms.items():
        kind, count = merged.get(ref, (_kind(clause), 0))
        merged[ref] = (kind, count + uses[clause])
    for ref, (kind, count) in merged.items():
        out.execute("INSERT INTO prereq_term VALUES (?,?,?)", (ref, kind, count))
    for clause, ref in terms.items():
        # A resolved sub-option already has its printed label in the index under
        # its own ref; overwriting it with the clause text would lose the name the
        # localisation is *for*.
        if not _SUB_OPTION.fullmatch(ref):
            names[ref] = {_key(clause, ordinary): clause}

    atoms = 0
    for row in rows:
        ref = f"f{row['ID']}"
        tree = trees[row["ID"]]
        opaque = _substitute(tree, terms)
        atoms += _count(tree)
        body = detail(row["Txt"] or "")
        cards = [m.start() for m in _HEAD.finditer(body) if _CARD.match(body, m.start())]
        head = body[: cards[0]] if cards else body
        tier = (row["Tier"] or "").strip()
        books = json.dumps(
            [b.strip() for b in (row["Source"] or "").split(",") if b.strip()]
        )
        card_description = ""
        for n, start in enumerate(cards, start=1):
            stop = next((h.start() for h in _HEAD.finditer(body, start + 1)), len(body))
            card_description = _card(
                body[start:stop], f"{ref}{chr(ord('a') + n)}", row, tier, books, out, names
            )
            report.feat_cards += 1
        out.execute(
            "INSERT INTO feat VALUES (?,?,?,?,?,?,?,?)",
            (
                ref, row["ID"], tier, _min_level(tree),
                json.dumps(tree) if tree else None, opaque,
                books, _trimmed(source, row, _benefit(head, ref, row["Name"] or "")),
            ),
        )
        names[ref] = {"name": (row["Name"] or "").strip(),
                      "description": card_description,
                      "rules_text": _rules_text(head)}
        report.feats += 1
        report.unparsed += opaque

    report.terms = len(terms)
    report.scores["feat"] = 1 - report.unparsed / max(1, atoms)


def _card(
    fragment: str,
    ref: str,
    row: sqlite3.Row,
    tier: str,
    books: str,
    out: sqlite3.Connection,
    names: dict[str, dict[str, str]],
) -> str:
    """One power card printed inside a feat, as a row of its own.

    Suffixed off the parent exactly as `power.parse_extra` suffixes a second
    card off a power, and for the same reason: the compendium files it under
    the feat's id, so a row that has to *name* the power the feat grants had
    nothing to point at. The gate stays on the parent -- `prereq` here is
    null and `unparsed` zero, or every opaque clause would be counted twice.
    """
    name = ""
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", fragment, re.S)
    if heading:
        name = text(heading.group(1))
        level = re.search(r'<span class="level">(.*?)</span>', fragment, re.S)
        if level:
            name = name.replace(text(level.group(1)), "").strip()
    spec = power_spec(fragment, ref, name)
    # And the parent feat's name, which `power_spec` does not know about: a
    # feat's card is very often named after the feat.
    parent = (row["Name"] or "").strip()
    if parent:
        spec = scrub(spec, {parent: f"f{row['ID']}"})
    out.execute(
        "INSERT INTO feat VALUES (?,?,?,?,?,?,?,?)",
        (ref, row["ID"], tier, 1, None, 0, books, spec),
    )
    # A card is read in the power dialect, so its printed rules are
    # `power_rules` -- the same lines `power_spec` scrubs two lines up. #349.
    names[ref] = {"name": name, "description": description(fragment),
                  "rules_text": power_rules(fragment)}
    return description(fragment)


def _rules_text(head: str) -> str:
    """The feat's printed rules text, **names left in**.

    The feat dialect puts the tier, the prerequisite and the benefit in one
    `<p class="flavor">` separated by `<br/>`, so `html.labelled` sees a
    single blob with one label on the front of it and `power_spec` would
    drop the lot. Splitting the paragraph's own lines is what reads it.

    An errata heading takes **the rest of its paragraph** with it, where
    the tier and the prerequisite take only themselves. The heading is
    followed by the instruction it introduces -- add a word to the second
    sentence, and so on -- and dropping the heading alone leaves an author
    reading an edit to the paragraph above as though it were a rule.

    **The rest of the paragraph, not the rest of the page's sections.**
    `_RESUMES` says where the block stops; see its note.
    """
    lines: list[str] = []
    for cls, para in paragraphs(head):
        if "publishedIn" in cls:
            continue
        erratum = False
        for line in text(para).split("\n"):
            bare = line.strip()
            if not bare:
                continue
            if _ERRATA.match(bare):
                erratum = True
                continue
            if _RESUMES.match(bare):
                erratum = False
            if erratum:
                continue
            if _FURNITURE.match(bare):
                continue
            lines.append(line)
    return "\n".join(lines)


def _benefit(head: str, ref: str, name: str) -> str:
    """The feat's rules text, scrubbed -- what an author is shown.

    `_rules_text` is the same lines with the name left in. One reader and two
    returns, for the reason `sanitise.power_spec` gives: the printed rules and
    the author-facing spec must not be two extractions. #349.
    """
    return scrub(_rules_text(head), {name: ref})


def _prerequisite(document: str) -> str:
    match = re.search(
        r"<b>\s*Prerequisite\s*</b>\s*:?\s*(.*?)(?=<br|</p|<h1)", document, re.S | re.I
    )
    return text(match.group(1)) if match else ""


class _Index:
    """The name tables a prerequisite clause is resolved against."""

    def __init__(
        self,
        source: sqlite3.Connection,
        out: sqlite3.Connection,
        names: dict[str, dict[str, str]],
        rows: list[sqlite3.Row],
    ) -> None:
        self.classes = {n.lower() for (n,) in out.execute("SELECT name FROM class")}
        self.features = _by_name(out, names, "SELECT ref FROM class_feature")
        self.powers = _by_name(out, names, "SELECT ref FROM power")
        self.feats = {
            _flat((r["Name"] or "").lower()): f"f{r['ID']}" for r in rows
        }
        # Races come from the table `item.races()` writes. While that parser
        # is still a stub the compendium's own rows stand in, on the same
        # `r<ID>` convention: without the fallback all ~690 race
        # prerequisites file as opaque terms, and a missing dependency looks
        # exactly like a broken parser.
        self.races = {
            name: refs[0]
            for name, refs in _by_name(out, names, "SELECT ref FROM race").items()
        } or {
            _flat((name or "").lower()): f"r{rid}"
            for rid, name in source.execute("SELECT ID, Name FROM Race")
        }


def _by_name(
    out: sqlite3.Connection, names: dict[str, dict[str, str]], sql: str
) -> dict[str, list[str]]:
    """Printed name to every ref that carries it.

    A list, not one ref: "Channel Divinity" is a class feature of four
    classes and the prerequisite does not say which, so the honest atom is
    an `any` over all of them rather than whichever row sorted first.
    """
    found: dict[str, list[str]] = {}
    for (ref,) in out.execute(sql):
        name = _flat((names.get(ref) or {}).get("name", "").lower())
        if name:
            found.setdefault(name, []).append(ref)
    return found


def _flat(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("\u2019", "'")).strip(" .")


def _tree(clause: str, index: _Index) -> dict:
    """The prerequisite as nested `all`/`any`, atoms at the leaves.

    Semicolons outrank commas outrank `or` outranks `and`, which is how the
    pages punctuate: `Shadar-kai; bard, sorcerer, or wizard class` is one
    race **and** one of three classes. A comma list is conjunctive unless
    its last item opens with "or", which is the only mark the prose gives
    that `Fighter, ranger, or warlord` means any of the three -- splitting
    it naively made two requirements and a third that was satisfied alone.
    """
    node = _flatten({"all": [_group(part, index) for part in _split(clause, (";",))]})
    return node if "all" in node else {"all": [node]}


def _flatten(node: dict) -> dict:
    """Drop the wrappers the split leaves behind.

    Four separators are tried in turn whether or not each one did anything,
    so a bare `Dex 13` arrives four levels deep and a plain comma list
    arrives inside a second `all`. Nothing reads such a tree *wrongly*, but
    everything reads it harder, and the point of the column is that a
    person can look at it.
    """
    for joiner in ("all", "any"):
        if joiner not in node:
            continue
        children: list[dict] = []
        for child in (_flatten(c) for c in node[joiner]):
            if joiner in child:
                children.extend(child[joiner])
            else:
                children.append(child)
        return children[0] if len(children) == 1 else {joiner: children}
    return node


def _group(part: str, index: _Index) -> dict:
    pieces = _split(part, (",",))
    if len(pieces) == 1:
        return _phrase(pieces[0], index)
    joiner = "any" if any(re.match(r"or\s", p, re.I) for p in pieces[1:]) else "all"
    return {
        joiner: [
            _phrase(re.sub(r"^(?:or|and)\s+", "", p, flags=re.I), index)
            for p in pieces
        ]
    }


def _phrase(part: str, index: _Index) -> dict:
    for sep, joiner in ((" or ", "any"), (" and ", "all")):
        pieces = _split(part, (sep,))
        if len(pieces) > 1:
            return {joiner: [_phrase(p, index) for p in pieces]}
    return _atom(part, index)


def _split(clause: str, seps: tuple[str, ...]) -> list[str]:
    """Split outside brackets. `Shield Proficiency (Heavy or Light)` is one
    requirement, and so is `Beast Mastery class feature (boar, lizard)`."""
    low = clause.lower()
    parts: list[str] = []
    depth = start = position = 0
    while position < len(clause):
        char = clause[position]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            hit = next((s for s in seps if low.startswith(s, position)), None)
            if hit:
                parts.append(clause[start:position])
                position += len(hit)
                start = position
                continue
        position += 1
    parts.append(clause[start:])
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _atom(clause: str, index: _Index) -> dict:
    """One clause as the narrowest safe thing it can be said to be.

    Order is deliberate. A class is tested before a race because `wizard
    class` is not a race, and both before the bare feat and power lookups,
    which are the loosest tests here -- a whole-clause match against 3,271
    feat names is strong evidence, but only for a clause of more than one
    word. Everything that survives is a printed name and stays opaque.
    """
    abilities, sources, skills = _vocabulary()
    low = _flat(clause.lower())

    level = re.fullmatch(r"(\d+)(?:st|nd|rd|th)[\s-]level", low) or re.fullmatch(
        r"level\s+(\d+)", low
    )
    if level:
        return {"level": int(level.group(1))}

    score = re.fullmatch(r"([a-z]+)\s+(\d+)", low)
    if score and score.group(1) in abilities:
        return {"ability": abilities[score.group(1)], "min": int(score.group(2))}

    trained = re.fullmatch(r"train(?:ed|ing)\s+(?:in|with)\s+(.+)", low)
    if (trained.group(1) if trained else low) in skills:
        return {"skill": trained.group(1) if trained else low}

    origin = re.fullmatch(r"(?:any\s+|multiclass\s+)?([a-z]+)\s+class", low)
    if origin and origin.group(1) in sources:
        return {"source": origin.group(1)}

    base, _, build = low.partition("(")
    base = re.sub(r"\s+class$", "", base).strip()
    if base in index.classes:
        atom = {"class": base}
        if build.rstrip(")").strip():
            atom["build"] = build.rstrip(")").strip()
        return atom

    race = re.sub(r"\s+race$", "", low)
    if race in index.races:
        return {"race": index.races[race]}

    if low.endswith("power"):
        # A class feature that *is* a power is printed as a card on the
        # class page and is a `cf:` row, so the clause "<name> power" is
        # as often a feature as a power and asking only `powers` filed
        # the feature's own name as an opaque term.
        found = index.powers.get(_bare_power(low)) or index.features.get(
            _bare_power(low)
        )
        if found:
            return _ref(found)

    feature = re.fullmatch(r"(.+?)\s+(?:class\s+)?feature", low)
    if feature and feature.group(1) in index.features:
        return _ref(index.features[feature.group(1)])

    feat = re.fullmatch(r"(.+?)\s+feat", low)
    if feat and feat.group(1) in index.feats:
        return {"ref": index.feats[feat.group(1)]}

    gear = re.fullmatch(r"(?:proficien(?:cy|t)|train(?:ing|ed))\s+(?:with|in)\s+(.+)", low)
    kit = re.sub(r"^(?:any|a|an|the)\s+", "", gear.group(1) if gear else low)
    if _is_gear(kit):
        return {"weapon_prof": kit}

    if " " in low:
        if low in index.feats:
            return {"ref": index.feats[low]}
        if low in index.powers:
            return _ref(index.powers[low])
        # **And a class feature named with no noun after it.** The pages
        # gate a feat on a build choice by printing the choice and
        # nothing else -- no "class feature", no "power" -- so the clause
        # is the bare printed name of a `cf:` row. 66 of the rows marked
        # `c.class_feature()` carried their own answer here and it was
        # filed as an opaque term beside them.
        #
        # Safe for the same reason the two lookups above it are: this is
        # a **whole-clause** match of more than one word against a table
        # of printed names, in a position where a prerequisite names
        # something the character must have. `identifies` is the test for
        # a phrase found loose in running prose, and would rightly waive
        # a two-word one -- there is no running prose here.
        if low in index.features:
            return _ref(index.features[low])

    return {"term": low}


def _bare_power(low: str) -> str:
    """`inspiring word encounter power` is the power called `inspiring word`."""
    name = re.sub(r"\s+power$", "", low)
    while True:
        shorter = re.sub(
            r"\s+(?:racial|encounter|daily|at-will|utility|attack|class)$", "", name
        )
        if shorter == name:
            return name
        name = shorter


def _ref(refs: list[str]) -> dict:
    return {"ref": refs[0]} if len(refs) == 1 else {"any": [{"ref": r} for r in refs]}


@lru_cache(maxsize=1)
def _gear_words() -> frozenset[str]:
    """Weapon and armour vocabulary, which is mechanics and not a name.

    `RULES_TERMS` already holds every weapon and armour the engine is
    entitled to say; the 4e *weapon groups* -- heavy blade, polearm -- are
    just as mechanical and happen not to be in it. Anything outside both is
    a printed name, and the Dark Sun weapons are invented words: filing one
    as a `weapon_prof` would put it straight into a spec, which is the whole
    failure this module exists to avoid.
    """
    words = {word for term in RULES_TERMS for word in term.split()}
    return frozenset(
        words
        | {
            "one-handed", "two-handed", "melee", "ranged", "superior",
            "military", "simple", "thrown", "versatile", "blade", "polearm",
        }
    )  # fmt: skip


def _is_gear(kit: str) -> bool:
    words = re.findall(r"[a-z-]+", kit)
    known = _gear_words()
    return bool(words) and all(w in known or w.rstrip("s") in known for w in words)


def _key(clause: str, ordinary: set[str]) -> str:
    """Which half of a `names.json` entry an opaque clause belongs in.

    `leaks.py` indexes `name` and not `description`, so anything put under
    `name` becomes a phrase it will hunt for in every tracked file. Two
    kinds of clause must stay out of that index:

    * a **whole sentence**, which would start matching ordinary prose in
      `docs/` a word at a time -- hence four words or fewer;
    * a clause made **entirely of words the corpus already treats as
      English**. "Wolf beast companion" is a printed prerequisite and also
      the plainest description of a ranger's pet, and indexing it reported
      a hand-written ranger row for saying what it does. The same test
      `build._creature_names` applies to a monster's name, for the same
      reason.
    """
    words = re.findall(r"[a-z']+", clause.lower())
    if len(clause.split()) > 4 or all(w in ordinary for w in words):
        return "description"
    return "name"


def _kind(clause: str) -> str:
    for pattern, kind in _KINDS:
        if re.search(pattern, clause, re.I):
            return kind
    return "other"


def _walk(node: dict | None) -> Iterator[dict]:
    if node is None:
        return
    for joiner in ("all", "any"):
        if joiner in node:
            for child in node[joiner]:
                yield from _walk(child)
            return
    yield node


def _opaque(node: dict | None) -> list[str]:
    return [leaf["term"] for leaf in _walk(node) if "term" in leaf]


def _count(node: dict | None) -> int:
    return sum(1 for _ in _walk(node))


def _substitute(node: dict | None, terms: dict[str, str]) -> int:
    """Swap each opaque clause's text for its id, in place. Returns how many."""
    swapped = 0
    for leaf in _walk(node):
        if "term" in leaf:
            leaf["term"] = terms[leaf["term"]]
            swapped += 1
    return swapped


def _min_level(node: dict | None) -> int:
    return max((leaf["level"] for leaf in _walk(node) if "level" in leaf), default=1)
