"""Building `data/game.db` from the compendium.

Destructive and idempotent: the database is recreated from scratch every
run, so the only way to change what is in it is to change a parser.

Two files come out, and **neither is redistributable**. Both are built from
your own copy of the compendium and both are gitignored:

* `data/game.db` -- every row's numbers, plus the mechanical text each was
  written from. The numbers are facts about a game system and not protectable;
  the text is the publisher's sentences, which is why this file does not ship.
  An earlier version of this docstring called it distributable, which was
  wrong the moment the specs went into it.
* `localization/names.json` -- ids to printed names and flavour.

What *is* distributable is `src/` -- the engine and the hand-written content,
which hold ids and mechanics and no prose at all. `scripts/leaks.py` is what
holds them to it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import monster as monster_parser
from . import power as power_parser

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "compendium.sqlite"
GAME = ROOT / "data" / "game.db"
NAMES = ROOT / "localization" / "names.json"

#: The project's scope, from the README: characters to 10, monsters to 13.
MAX_POWER_LEVEL = 10
MAX_MONSTER_LEVEL = 13
#: The eight Player's Handbook classes. Powers from later books are
#: still ingested for these classes -- the `source` column says which
#: book a row came from, so narrowing to PHB1 is a query and not a
#: rebuild.
#:
#: Every class except the hybrids. The eight Player's Handbook ones came
#: first and were the whole list for a long while; the rest are here so
#: their powers are in the database at all -- a class still needs a
#: `chargen.ClassLine` before any of its rows mean anything.
CLASSES = (
    "Cleric", "Fighter", "Paladin", "Ranger",
    "Rogue", "Warlock", "Warlord", "Wizard",
    "Ardent", "Artificer", "Assassin", "Avenger", "Barbarian", "Bard",
    "Battlemind", "Druid", "Invoker", "Monk", "Psion", "Runepriest",
    "Seeker", "Shaman", "Sorcerer", "Swordmage", "Warden",
)  # fmt: skip

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE monster (
  ref TEXT PRIMARY KEY, id INTEGER, level INTEGER, role TEXT,
  minion INTEGER, leader INTEGER, elite INTEGER, solo INTEGER,
  size TEXT, origin TEXT, kind TEXT, keywords TEXT, xp INTEGER,
  hp INTEGER, ac INTEGER, fort INTEGER, ref_def INTEGER, will INTEGER,
  initiative INTEGER, speed INTEGER, modes TEXT, scores TEXT,
  resist TEXT, vulnerable TEXT, immune TEXT, senses TEXT,
  book TEXT, rank TEXT,
  dialect TEXT, score REAL
);
CREATE INDEX monster_book ON monster(book, level);
CREATE INDEX monster_level ON monster(level, role);

CREATE TABLE monster_power (
  ref TEXT PRIMARY KEY, monster_ref TEXT, idx INTEGER, section TEXT,
  usage TEXT, action TEXT, recharge INTEGER, keywords TEXT, spec TEXT
);
CREATE INDEX monster_power_owner ON monster_power(monster_ref);

CREATE TABLE common_word (
  word TEXT PRIMARY KEY, documents INTEGER
);

CREATE TABLE power (
  ref TEXT PRIMARY KEY, id INTEGER, class TEXT, level INTEGER,
  usage TEXT, action TEXT, kind TEXT, reach TEXT, keywords TEXT,
  books TEXT, spec TEXT, score REAL
);
CREATE INDEX power_class ON power(class, level);

CREATE TABLE class (
  name TEXT PRIMARY KEY, role TEXT, source TEXT,
  hp_first INTEGER, hp_per_level INTEGER, surges INTEGER,
  defences TEXT, armour TEXT, weapons TEXT, implements TEXT,
  abilities TEXT
);

-- The features themselves, which `class` above never carried. Only the
-- chassis numbers were read off the page, so every `cf:` ref in the tree
-- was written from a paraphrase or guessed outright -- and `spec.py`
-- answered "no such row" for all of them, which read as "this feature
-- has no printed text" rather than "nobody imported it".
--
-- Keyed by page order rather than by name: the name is trademarked and
-- lives in `localization/names.json` with every other printed name, so a
-- ref can be written into tracked source and `leaks.py` stays honest.
CREATE TABLE class_feature (
  ref TEXT PRIMARY KEY, class TEXT, ord INTEGER, build TEXT, spec TEXT
);
CREATE INDEX class_feature_class ON class_feature(class, ord);
"""


@dataclass
class Report:
    monsters: int = 0
    abilities: int = 0
    powers: int = 0
    classes: int = 0
    features: int = 0
    seconds: int = 0
    crossed: int = 0
    names: int = 0
    common: int = 0
    scores: dict[str, float] = field(default_factory=dict)
    worst: list[tuple[str, float]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"monsters      {self.monsters:6d}",
            f"  abilities   {self.abilities:6d}",
            f"powers        {self.powers:6d}",
            f"classes       {self.classes:6d}",
            f"features      {self.features:6d}  (class features, new)",
            f"second cards  {self.seconds:6d}  (a card printed inside another entry)",
            f"cross-refs    {self.crossed:6d}  (specs naming another power, now by ref)",
            f"names         {self.names:6d}  (localization/names.json, gitignored)",
            f"common words  {self.common:6d}  (what leaks.py treats as English)",
            "",
            "parse coverage",
        ]
        for k, v in sorted(self.scores.items()):
            lines.append(f"  {k:<12s} {v:6.3f}")
        if self.worst:
            lines += ["", "worst-parsed rows, look here first"]
            lines += [f"  {ref:<12s} {score:.2f}" for ref, score in self.worst]
        return "\n".join(lines)


def connect() -> sqlite3.Connection:
    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} is missing.\n"
            "It is ~140MB of copyrighted content and is not distributed with "
            "this repository. Put your own copy at the project root."
        )
    db = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def build() -> Report:
    source = connect()
    GAME.parent.mkdir(parents=True, exist_ok=True)
    NAMES.parent.mkdir(parents=True, exist_ok=True)
    GAME.unlink(missing_ok=True)

    out = sqlite3.connect(GAME)
    out.executescript(SCHEMA)
    report = Report()
    names: dict[str, dict[str, str]] = {}

    _monsters(source, out, report, names)
    _powers(source, out, report, names)
    report.classes = _classes(source, out)
    report.features = _features(source, out, names)
    _common_words(source, out, report)

    out.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("source_sha256", _digest(SOURCE)),
    )
    out.commit()
    out.close()

    NAMES.write_text(json.dumps(names, indent=1, sort_keys=True))
    localisation.cache_clear()
    report.names = len(names)
    return report


def _monsters(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Report,
    names: dict[str, dict[str, str]],
) -> None:
    scores: list[float] = []
    rows = list(source.execute(
        "SELECT ID, Txt, Source FROM Monster WHERE Level <= ? ORDER BY ID",
        (MAX_MONSTER_LEVEL,),
    ))
    # One pass to learn every creature's name, then the real one. A stat
    # block that names a *different* creature could not be scrubbed before,
    # because the scrubber only knew the one it was working on -- so 233
    # specs carried somebody else's printed name straight through to an
    # author who is not allowed to see one.
    index = _creature_names(rows)
    for row in rows:
        m = monster_parser.parse(row["ID"], row["Txt"], row["Source"], others=index)
        scores.append(m.score)
        report.monsters += 1
        report.worst.append((m.ref_id, m.score))
        out.execute(
            "INSERT INTO monster VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.ref_id, m.id, m.level, m.role,
                int(m.minion), int(m.leader), int(m.elite), int(m.solo),
                m.size, m.origin, m.kind, json.dumps(m.keywords), m.xp,
                m.hp, m.ac, m.fort, m.ref, m.will,
                m.initiative, m.speed, json.dumps(m.modes), json.dumps(m.scores),
                json.dumps(m.resist), json.dumps(m.vulnerable), json.dumps(m.immune),
                m.senses, m.book, m.rank, m.dialect, m.score,
            ),
        )
        names[m.ref_id] = {"name": m.name, "flavour": m.flavour}
        for a in m.abilities:
            ref = f"{m.ref_id}a{a.index}"
            out.execute(
                "INSERT INTO monster_power VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    ref, m.ref_id, a.index, a.section, a.usage, a.action,
                    a.recharge, json.dumps(a.keywords), a.spec,
                ),
            )
            names[ref] = {"name": a.name}
            report.abilities += 1
    report.scores["monster"] = sum(scores) / max(1, len(scores))
    report.worst = sorted(report.worst, key=lambda p: p[1])[:10]


def _creature_names(rows: list) -> dict[str, str]:
    """Every creature's printed name, mapped to its ref.

    Names made entirely of words the engine already has are left out -- the
    ones built from a damage type and a keyword are the common case. Replacing those would
    corrupt a spec that merely used the words, which is worse than the leak:
    an author would be handed mechanics with rules terms swapped for ids.
    """
    from .sanitise import mechanical

    def worth_swapping(name: str) -> bool:
        words = re.findall(r"[A-Za-z']+", name.lower())
        return bool(words) and len(name) >= 5 and not all(
            w in mechanical() for w in words
        )

    out: dict[str, str] = {}
    for row in rows:
        m = monster_parser.parse(row["ID"], row["Txt"], row["Source"])
        if worth_swapping((m.name or "").strip()):
            out.setdefault(m.name.strip(), m.ref_id)
        # Ability names too. A stat block saying "recharges after the use of
        # <another creature's power>" leaks that power's name exactly as a
        # creature's name leaked, and its ref is just as usable.
        for a in m.abilities:
            nm = (a.name or "").strip()
            if worth_swapping(nm):
                out.setdefault(nm, f"{m.ref_id}a{a.index}")
    return out


#: The chassis lines every class page prints, in the order they appear.
#: Read out of the compendium rather than transcribed: seventeen classes
#: are too many to copy by hand without a mistake, and a number nobody can
#: trace back to a page is a number nobody can check.
_CHASSIS = {
    "hp_first": r"Hit Points at 1st Level\s*:?\s*(\d+)",
    "hp_per_level": r"Hit Points per Level Gained\s*:?\s*(\d+)",
    "surges": r"Healing Surges(?: per Day)?\s*:?\s*(\d+)",
    "armour": r"Armor Proficiencies\s*:?\s*([^.]+)",
    "weapons": r"Weapon Proficiencies\s*:?\s*([^.]+)",
    "implements": r"Implements?\s*:?\s*([^.]+)",
    "defences": r"Bonus to Defenses?\s*:?\s*([^.]+)",
}


def _classes(source: sqlite3.Connection, out: sqlite3.Connection) -> int:
    """Every non-hybrid class's chassis, off its own page.

    `chargen` needs hit points, surges, defence bonuses and proficiencies
    before a class's powers mean anything, and the eight that exist were
    hand-written. Seventeen more by hand is seventeen chances to mistype a
    number that nothing would catch -- the powers would all work and the
    character would quietly be wrong.
    """
    # Matched on the bare name, because the compendium files a class under
    # its *build*: "Cleric (Templar)", "Fighter (Weaponmaster)", and six
    # separate wizards. Asking for exact names found the twenty classes
    # that have only one build and missed the five that were here first.
    #
    # Hybrids are excluded by name -- they are a way of combining two
    # classes rather than a class, and the goal says so.
    written = 0
    wanted = {c.lower() for c in CLASSES}
    rows = [
        r
        for r in source.execute(
            "SELECT Name, Role, Source, Abilities, PlainTxt, Txt FROM Class"
        )
        if not r["Name"].lower().startswith("hybrid")
        and r["Name"].split("(")[0].strip().lower() in wanted
    ]
    # One row per class: the earliest printing, which is the one the other
    # books amend rather than replace.
    seen: set[str] = set()
    for row in rows:
        bare = row["Name"].split("(")[0].strip()
        if bare in seen:
            continue
        seen.add(bare)
        plain = row["PlainTxt"] or re.sub(r"<[^>]+>", " ", row["Txt"] or "")
        found: dict[str, str] = {}
        for field_, pattern in _CHASSIS.items():
            m = re.search(pattern, plain, re.I)
            if m:
                found[field_] = m.group(1).strip()
        out.execute(
            "INSERT OR REPLACE INTO class VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                bare, row["Role"] or "", row["Source"] or "",
                int(found.get("hp_first", 0) or 0),
                int(found.get("hp_per_level", 0) or 0),
                int(found.get("surges", 0) or 0),
                found.get("defences", ""), found.get("armour", ""),
                found.get("weapons", ""), found.get("implements", ""),
                row["Abilities"] or "",
            ),
        )
        written += 1
    return written



#: A feature heading inside the class-features section: the page sets each
#: in bold capitals. Lower-case bold is a *sub-option* of the feature above
#: it ("Centered Breath" under MONASTIC TRADITION), which is why the case
#: matters and a bare `<b>` would run them together.
_TRAILING_ESSAY = re.compile(
    r"<br\s*/?>\s*<br\s*/?>\s*[A-Z][A-Z0-9 \u2019'&/-]{6,}\s*<br"
)

_FEATURE_HEAD = re.compile(r"<b>\s*([A-Z][A-Z0-9 \u2019'&/-]{3,60}?)\s*</b>")


def _features(source: sqlite3.Connection, out: sqlite3.Connection,
              names: dict[str, dict[str, str]]) -> int:
    """Every class feature's printed rules text, off the class page.

    `_classes` above reads the same pages and keeps only the chassis
    numbers, so the features were dropped on the floor -- and because
    `spec.py` had nothing to answer with, every `cf:` ref in the tree was
    written from a paraphrase in `docs/blocked.json` or guessed. Five
    classes have no `Feature` power row at all, so for those it was
    guesswork all the way down.

    **Every build, not just the earliest printing.** `_classes` keeps one
    row per class on the grounds that later books amend rather than
    replace; that is right for hit points and wrong for features, because
    a build *is* a different set of them.
    """
    written = 0
    wanted = {c.lower() for c in CLASSES}
    for row in source.execute(
        "SELECT Name, Txt FROM Class ORDER BY Name"
    ):
        name = row["Name"] or ""
        bare = name.split("(")[0].strip()
        if name.lower().startswith("hybrid") or bare.lower() not in wanted:
            continue
        build = name.partition("(")[2].rstrip(")").strip()
        html = row["Txt"] or ""
        # The section is its own heading. Anything before it is the
        # chassis and the build summaries; anything after is prose about
        # deities and party role.
        start = re.search(r"<h3[^>]*>[^<]*CLASS FEATURES[^<]*</h3>", html, re.I)
        if start is None:
            continue
        rest = html[start.end():]
        end = re.search(r"<h3[^>]*>", rest)
        section = rest[: end.start()] if end else rest
        heads = list(_FEATURE_HEAD.finditer(section))
        for i, m in enumerate(heads):
            stop = heads[i + 1].start() if i + 1 < len(heads) else len(section)
            body = section[m.end(): stop]
            # A feature that *is* a power is already a `Feature` row in
            # `power`, embedded here as its own card. Keep the prose that
            # introduces it and drop the card, so the two do not disagree.
            body = re.sub(r"<h1\b.*", "", body, flags=re.S)
            # The page ends the feature list with a bare uppercase run --
            # no tag at all, just `<br/><br/>SWORDMAGE OVERVIEW<br/>` --
            # so the last feature of every class swallowed the essay about
            # deities and party role that follows it.
            body = _TRAILING_ESSAY.split(body, 1)[0]
            from .html import text as _text

            spec = " ".join(_text(body).split())
            if len(spec) < 20:
                continue
            ref = f"cf:{bare.lower()}-f{i}" if not build else (
                f"cf:{bare.lower()}-{_slug(build)}-f{i}"
            )
            out.execute(
                "INSERT OR REPLACE INTO class_feature VALUES (?,?,?,?,?)",
                (ref, bare, i, build, spec),
            )
            names[ref] = {"name": m.group(1).title()}
            written += 1
    return written


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

def _powers(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Report,
    names: dict[str, dict[str, str]],
) -> None:
    scores: list[float] = []
    marks = ",".join("?" * len(CLASSES))
    rows = source.execute(
        f"SELECT * FROM Power WHERE Level <= ? AND Class IN ({marks}) ORDER BY ID",
        (MAX_POWER_LEVEL, *CLASSES),
    )
    def keep(p: power_parser.Power) -> None:
        out.execute(
            "INSERT INTO power VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                p.ref, p.id, p.cls, p.level, p.usage, p.action, p.kind,
                p.reach, json.dumps(p.keywords), json.dumps(p.books),
                p.spec, p.score,
            ),
        )
        names[p.ref] = {"name": p.name, "flavour": p.flavour}

    for row in rows:
        p = power_parser.parse(dict(row), row["Txt"])
        scores.append(p.score)
        report.powers += 1
        keep(p)
        # A second card printed inside the same entry. The compendium files
        # both under one id, so a row that must *name* the second -- "you
        # regain the use of that form's attack" -- had nothing to point at,
        # and three rows were recorded unwritable for want of an id that
        # could simply be derived from the parent's.
        for extra in power_parser.parse_extra(dict(row), row["Txt"]):
            report.seconds += 1
            keep(extra)
    report.scores["power"] = sum(scores) / max(1, len(scores))
    report.crossed = _cross_reference(out, names)


def _cross_reference(out: sqlite3.Connection, names: dict[str, dict[str, str]]) -> int:
    """Swap one power's name for its ref wherever another power prints it.

    Monsters have had this since they were imported (`etl/monster.py`);
    powers never did, so a row whose whole Effect is "you regain the use
    of <another power>" printed that name to anyone reading the spec --
    and, worse, gave the person writing it **no ref to name**. Two rows
    were recorded as unwritable on exactly that.

    Same class and two words minimum. A cross-class reference is
    vanishingly rare and a one-word power name is very often an ordinary
    verb; both would trade a real leak for a lot of false ones.
    """
    from .sanitise import scrub

    by_class: dict[str, dict[str, str]] = {}
    for ref, cls in out.execute("SELECT ref, class FROM power"):
        name = (names.get(ref) or {}).get("name", "")
        if len(name.split()) > 1:
            by_class.setdefault(cls, {})[name] = ref

    changed = 0
    for ref, cls, spec in out.execute("SELECT ref, class, spec FROM power").fetchall():
        others = {n: r for n, r in by_class.get(cls, {}).items() if r != ref}
        if not others:
            continue
        fixed = scrub(spec, others)
        if fixed != spec:
            out.execute("UPDATE power SET spec=? WHERE ref=?", (fixed, ref))
            changed += 1
    return changed


#: A word used on the pages of at least this many rows is ordinary English.
#: `retreat` and `skeleton` turn up all over; a proper name turns up in its
#: own entry and its few variants.
COMMON_IN = 8


def _vocabulary(texts) -> set[str]:  # noqa: ANN001
    """The distinct words one row uses. A set, so this counts rows not uses."""
    import re

    out: set[str] = set()
    for chunk in texts:
        out.update(re.findall(r"[a-z]{2,}", (chunk or "").lower()))
    return out


def _common_words(
    source: sqlite3.Connection, out: sqlite3.Connection, report: Report
) -> None:
    """Record which words are ordinary English, measured by how widely used.

    `scripts/leaks.py` needs to tell a proper name from a word that merely
    happens to be one -- somebody published abilities called `Retreat` and
    `Stable`, and a power called `Not It`. Counting how many different rows
    use a word answers that from the data, so no hand-kept list of exceptions
    has to be fed forever.

    The corpus is every monster and power page in full, names and prose
    included, and not the sanitised specs -- a stat block's mechanics almost
    never say "skeleton", while the pages plainly do.
    """
    seen: Counter[str] = Counter()
    for table in ("Monster", "Power"):
        for row in source.execute(f"SELECT PlainTxt FROM {table}"):
            seen.update(_vocabulary([row[0]]))
    rows = [(w, n) for w, n in seen.items() if n >= COMMON_IN]
    out.executemany("INSERT INTO common_word VALUES (?, ?)", rows)
    report.common = len(rows)


def _digest(path: Path) -> str:
    """A hash of the source, so a different community build is detectable."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=1)
def _open_game() -> sqlite3.Connection:
    if not GAME.exists():
        raise SystemExit(f"{GAME} is missing. Run: uv run scripts/build.py")
    db = sqlite3.connect(f"file:{GAME}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def game() -> sqlite3.Connection:
    """The built database. The engine reads this, never the compendium.

    One connection per process. It used to open a fresh one on every call,
    and `loader.spawn` calls it several times per creature -- so building an
    audit board opened six connections, and an audit builds a hundred
    thousand boards. Read-only, so sharing it is safe; `check_same_thread`
    is off because the API serves its blocking handlers from a threadpool.
    """
    return _open_game()


@lru_cache(maxsize=1)
def localisation() -> dict[str, dict[str, str]]:
    """Printed names, if this machine has them. The engine never calls this.

    Cached: it is seventeen thousand entries, it is read once per name looked
    up, and re-parsing it each time was a quarter of the time taken to draw
    the board. Call `localisation.cache_clear()` after a rebuild.
    """
    if not NAMES.exists():
        return {}
    return json.loads(NAMES.read_text())


if __name__ == "__main__":
    print(build().render())
