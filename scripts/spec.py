#!/usr/bin/env python
"""What to hand somebody who is about to write a power.

    uv run scripts/spec.py p289              one power
    uv run scripts/spec.py m145              a monster: its numbers, then each ability
    uv run scripts/spec.py i601              an item: its columns, then each block
    uv run scripts/spec.py f3                a feat: its gate, then the benefit
    uv run scripts/spec.py b:c134-0          a build leg: its fork and its set
    uv run scripts/spec.py --class fighter --level 1
    uv run scripts/spec.py --monsters 1 --role brute
    uv run scripts/spec.py --items --slot weapon --level 3 --limit 20
    uv run scripts/spec.py --feats --class fighter --limit 20
    uv run scripts/spec.py --class rogue --level 1 --all

By default only rows that have **not** been declared yet come out, so the
output is a work list rather than a catalogue.

What comes out is the mechanical lines and nothing else. No name, no flavour
text, and no self-reference: a stat block that names itself in its own rules
says "contracts m145 filth fever" here instead. The author writes the function
without ever learning what the row is called, which is the arrangement that
keeps the engine free of a publisher's prose.

**Use `--limit`.** The heroic tier is 2,491 item blocks and 2,536 feats, and
the implement slot alone is 412 items; an unbounded `--items` is a brief
nobody can read and a context nobody can afford.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from combat_engine.etl.build import game

#: Heroic is `tier` when the page printed one and `min_level` when it did
#: not. `etl/feat.py` argues it; `coverage.py` asks the same question.
HEROIC = "(tier = 'Heroic' OR (tier = '' AND min_level <= 10))"

#: The project's scope, and the reason a ladder prints two rungs here and
#: not six: the paragon and epic ones are recorded but nobody is writing
#: against them, and six rungs on one line buried the two that matter.
#:
#: **Read from the ETL rather than held again.** This was its own `= 10`, so the
#: ceiling lived in two places and raising one would have left briefs printing two
#: rungs of a six-rung ladder with nothing saying why. The ETL owns what was
#: imported; an instrument describing the import cannot own it too. #281.
try:
    from combat_engine.etl.item import MAX_ITEM_LEVEL
except Exception:  # an instrument should still run without a built database
    MAX_ITEM_LEVEL = 10

#: `item.enh_to` is a code, because the pages word the same bonus eleven
#: ways. This is the wording an author needs to recognise it by.
ENHANCES = {
    "attack_damage": "attack rolls and damage rolls",
    "ac": "AC",
    "defences": "Fortitude, Reflex and Will",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("refs", nargs="*", help="any id, e.g. p289 m145 i601 i601x1 f3 r5")
    ap.add_argument("--class", dest="cls", help="a class; narrows powers or --feats")
    ap.add_argument(
        "--level",
        type=int,
        action="append",
        help="power level, or an item's base level; repeatable, because a "
        "class's level 0 and level 1 belong in one brief and two runs "
        "concatenated end with a spurious 'nothing to write' that two agents "
        "in a row reported as a lie",
    )
    ap.add_argument("--monsters", type=int, help="every monster at this level")
    ap.add_argument("--role", help="narrow --monsters to one role")
    ap.add_argument(
        "--mm13",
        action="store_true",
        help="--monsters: only the three Monster Manuals, which was the old "
        "default and is 630 of 3,130 imported monsters",
    )
    ap.add_argument("--items", action="store_true", help="magic items, heroic tier")
    ap.add_argument("--slot", help="narrow --items to one slot: weapon, implement, neck ...")
    ap.add_argument("--feats", action="store_true", help="feats, heroic tier")
    ap.add_argument("--general", action="store_true",
                    help="narrow --feats to those gated on no class and no race")
    ap.add_argument("--race", action="store_true", help="narrow --feats to the race-gated")
    ap.add_argument(
        "--book",
        default="Player's Handbook",
        help="only powers printed in this book; empty string for any",
    )
    ap.add_argument(
        "--features",
        action="store_true",
        help="the class features of --class, which live on the class page",
    )
    ap.add_argument("--all", action="store_true", help="include rows already declared")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many rows")
    ap.add_argument(
        "--offset",
        type=int,
        default=0,
        help="skip this many first. With --limit, how two authoring agents "
        "take disjoint halves of one slot without being handed a list of "
        "refs each -- the order is deterministic, so offset 0 and offset "
        "120 never overlap.",
    )
    args = ap.parse_args()

    db = game()
    declared = _declared()

    if args.features:
        return _features(db, args.cls)

    # `--class` means one thing for powers and another for feats, so the
    # three list modes are exclusive rather than additive: `--feats --class
    # fighter` must not also pour out the fighter's powers.
    wants_items = args.items or bool(args.slot)
    wants_feats = args.feats or args.general or args.race

    refs: list[str] = list(args.refs)
    if wants_items:
        refs += _item_refs(db, args.slot, args.level)
    elif wants_feats:
        refs += _feat_refs(db, args.cls, args.general, args.race)
    elif args.cls or args.level:
        refs += _powers(db, args.cls, args.level, args.book)
    if args.monsters is not None:
        refs += _monsters(db, args.monsters, args.role, book=args.mm13)
    if not refs:
        # Only help when nothing was *asked*. Filters that match nothing
        # used to print usage too, which reads as "you typed it wrong"
        # -- and the commonest cause is the book filter, which defaults
        # to the Player's Handbook and so silently empties any query
        # about a class printed in a later book.
        if args.cls or args.level or args.monsters is not None or wants_items or wants_feats:
            print(
                "# nothing matched those filters."
                + (f"  --book {args.book!r} excludes later books; try --book ''"
                   if args.book and not (wants_items or wants_feats) else ""),
                file=sys.stderr,
            )
            return 1
        ap.print_help()
        return 1

    shown = 0
    missing = 0
    for ref in refs:
        if not args.all and ref in declared:
            continue
        block = _render(db, ref, declared, args.all)
        if block is None:
            print(f"# {ref}: no such row", file=sys.stderr)
            missing += 1
            continue
        if not block:
            # A parent whose every child is declared. Distinct from `None`,
            # which is a typo, and it must not be reported as one.
            continue
        shown += 1
        if shown <= args.offset:
            continue
        print(block)
        print()
        if args.limit and shown - args.offset >= args.limit:
            break

    if shown <= args.offset:
        # **Two mutually exclusive messages used to come out together.** A ref
        # that resolved to nothing printed "no such row" and then this line,
        # which claims the opposite -- that it exists and is finished. An
        # author cannot tell a typo from a completed row from that pair.
        if missing:
            print(f"# nothing to write -- {missing} ref(s) resolved to no row")
        else:
            print("# nothing to write -- every row asked for is already declared")
    return 1 if missing else 0


def _features(db, cls: str | None) -> int:  # noqa: ANN001
    """Every class feature's printed text, which nothing could ask for.

    The features were never imported -- `class` carried the chassis
    numbers and nothing else -- so `spec.py` answered "no such row" for
    every `cf:` ref, and each one read as a feature with no printed text
    rather than one nobody had loaded. What got written instead was the
    paraphrase in `docs/blocked.json`, or a guess.

    Listed per class rather than per ref because the tree's `cf:` refs are
    hand-chosen descriptions and these are numbered by page order; the two
    are matched by reading, which is the point.
    """
    rows = db.execute(
        "SELECT ref, class, build, spec FROM class_feature"
        + (" WHERE lower(class)=?" if cls else "")
        + " ORDER BY class, build, ord",
        (cls.lower(),) if cls else (),
    ).fetchall()
    if not rows:
        print(f"# no class features for {cls or 'any class'}", file=sys.stderr)
        return 1
    for row in rows:
        build = f" ({row['build']})" if row["build"] else ""
        print(f"### {row['ref']}   {row['class']}{build}")
        print(row["spec"])
        print()
    return 0


def _declared() -> set[str]:
    from combat_engine.content import declared

    return set(declared())


def _powers(db, cls: str | None, levels: list[int] | None, book: str = "") -> list[str]:  # noqa: ANN001
    """Powers matching the filters, in a stable order.

    `book` is a membership test rather than a LIKE: `Source` is a
    comma-separated list and a row often names five books, so matching by
    substring picks up everything.
    """
    import json

    where, params = [], []
    if cls:
        where.append("lower(class) = ?")
        params.append(cls.lower())
    if levels:
        where.append("level IN (" + ",".join("?" * len(levels)) + ")")
        params.extend(levels)
    sql = "SELECT ref, books FROM power"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY class, level, ref"
    return [
        r["ref"]
        for r in db.execute(sql, params)
        if not book or book in json.loads(r["books"] or "[]")
    ]


def _monsters(db, level: int, role: str | None, book: bool = False) -> list[str]:  # noqa: ANN001
    """Monsters at a level. **Every imported source, not MM1-3.**

    This filtered on `book != ''` and its docstring asserted that was the
    scope. It is not: 630 of the 3,130 imported monsters carry a book, and
    those 630 are **exactly the ones already written** -- so the one tool that
    briefs an author could not list a single one of the 10,802 outstanding
    abilities. `coverage.py` had the same defect and the same fix in #357;
    `--mm13` keeps the old view.

    The per-ref path was never affected -- naming a ref has always worked --
    which is why this went unnoticed: an author could be briefed, but a wave
    could not be listed.
    """
    sql = "SELECT ref FROM monster WHERE level = ?"
    params: list = [level]
    if book:
        sql += " AND book != ''"
    if role:
        sql += " AND role = ?"
        params.append(role)
    return [r["ref"] for r in db.execute(sql + " ORDER BY ref", params)]


def _item_refs(db, slot: str | None, levels: list[int] | None) -> list[str]:  # noqa: ANN001
    """Items with at least one block, which is the only kind worth listing.

    37 heroic items have no Property and no Power at all: their whole rule
    is the enhancement bonus and the critical line, both columns, and there
    is nothing for anybody to write. Listing them put finished items in a
    work list.
    """
    where, params = [], []
    if slot:
        where.append("i.slot = ?")
        params.append(slot.lower())
    if levels:
        where.append("i.base_level IN (" + ",".join("?" * len(levels)) + ")")
        params.extend(levels)
    sql = "SELECT DISTINCT i.ref, i.base_level FROM item i JOIN item_block b ON b.item_ref = i.ref"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return [r["ref"] for r in db.execute(sql + " ORDER BY i.base_level, i.ref", params)]


def _feat_refs(db, cls: str | None, general: bool, race: bool) -> list[str]:  # noqa: ANN001
    """Heroic feats, optionally narrowed to one shelf.

    The gate is read off the whole table and not just the heroic slice,
    because a power card carries no prerequisite of its own -- it shares
    its parent's `id` and the parent holds the gate.
    """
    gates = {
        r["id"]: _gate(r["prereq"])
        for r in db.execute("SELECT id, prereq FROM feat WHERE prereq IS NOT NULL")
    }
    out = []
    for row in db.execute(f"SELECT ref, id FROM feat WHERE {HEROIC} ORDER BY id, ref"):
        gate = gates.get(row["id"], "general")
        if cls and gate != cls.lower():
            continue
        if general and gate != "general":
            continue
        if race and gate != "race":
            continue
        out.append(row["ref"])
    return out


def _gate(prereq: str | None) -> str:
    """Which shelf a feat sits on: a class, `race`, or `general`. Class
    outranks race, since a feat gated on both is a class feat one race may
    also take, and filing it under race hides it from the class."""
    leaves = list(_leaves(json.loads(prereq) if prereq else None))
    for leaf in leaves:
        if "class" in leaf:
            return leaf["class"]
    return "race" if any("race" in leaf for leaf in leaves) else "general"


def _leaves(node: dict | None):  # noqa: ANN202
    if not node:
        return
    for joiner in ("all", "any"):
        if joiner in node:
            for child in node[joiner]:
                yield from _leaves(child)
            return
    yield node


def _render(db, ref: str, declared: set[str], include_all: bool) -> str | None:  # noqa: ANN001
    # The new prefixes go first. `comp:` and `cf:` are already here for the
    # same reason: the `p` and `m` branches below are bare first-letter
    # tests, and the day a ref shaped `i601p1` reaches one of them it is
    # read as a power that does not exist.
    if ref.startswith("q"):
        return _term(db, ref)
    if ref.startswith("b:"):
        row = db.execute(
            "SELECT * FROM build_option WHERE ref = ?", (ref,)
        ).fetchone()
        if row is None:
            return None
        # **The fork is in the header, not the body**, because it is the one
        # thing on a leg that is a number rather than a reference, and a leg
        # states neither ability almost a third of the time -- 8 sections say
        # nothing about one at all and 15 more say something the two readers
        # in `etl/build.py` disagree about. A blank here means *the page did
        # not say*, which is why it is shown as a blank and not guessed. #235.
        fork = ", then ".join(
            filter(None, (row["ability"], row["second"]))
        ) or "fork unstated"
        count = db.execute(
            "SELECT count(*) FROM build_option WHERE class = ?", (row["class"],)
        ).fetchone()[0]
        return (
            f"### {row['ref']}   build option {row['ord'] + 1} of {count}"
            f" of {row['class'].lower()}   ({fork})\n{row['spec']}"
        )
    if ref.startswith("r") and re.fullmatch(r"r\d+", ref):
        row = db.execute("SELECT * FROM race WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        return f"### {row['ref']}   race   {row['size']}\n{row['spec']}"
    if ref.startswith("rt:"):
        # **Before the `r\d+` test is not enough -- it has to be before `r`
        # alone would do.** `rt:` is excluded from the race branch above by
        # its `fullmatch`, and then nothing claimed it, so every one of the
        # 151 traits fell off the end of this function and came back "no such
        # row" -- including the declared ones, which is what made #415 look
        # like a coverage problem rather than a dispatch one.
        row = db.execute(
            "SELECT * FROM racial_trait WHERE ref = ?", (ref,)
        ).fetchone()
        if row is None:
            return None
        # **The `slug` column is deliberately not printed.** It holds the
        # trait's own printed label for 147 of the 151 rows, so putting it in
        # a brief would hand an author the name this tool exists to withhold.
        # The race ref and the position are the identity; see #433.
        return (
            f"### {row['ref']}   racial trait of {row['race']}"
            f"   (trait {row['ord']})\n{row['spec']}"
        )
    if ref.startswith("i"):
        return _item(db, ref, declared, include_all)
    if ref.startswith("f"):
        return _feat(db, ref)
    if ref.startswith("comp:"):
        row = db.execute("SELECT * FROM companion WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        return f"### {row['ref']}   {row['kind']}\n{row['spec']}"
    if ref.startswith("cf:"):
        row = db.execute(
            "SELECT * FROM class_feature WHERE ref = ?", (ref,)
        ).fetchone()
        if row is None:
            return None
        build = f" ({row['build']})" if row["build"] else ""
        return f"### {row['ref']}   {row['class']}{build}\n{row['spec']}"
    if ref.startswith("p"):
        row = db.execute("SELECT * FROM power WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        head = (
            f"### {row['ref']}   {row['class']} level {row['level']}   "
            f"{row['usage']} / {row['action']}"
        )
        kw = json.loads(row["keywords"] or "[]")
        if kw:
            head += f"   keywords: {', '.join(kw)}"
        return f"{head}\n{row['spec']}"

    if ref.startswith("m"):
        # **One ability, asked for by ref.** Same argument as `_item`'s block
        # branch, and the same fix: a bare `m1003a0` used to fall through to
        # the `monster` lookup below, miss, and come back "no such row" -- so
        # the only way to read one ability was to ask for its whole creature
        # and find it by eye. The stat block comes with it, because the
        # numbers are most of what the row needs.
        only = ""
        if re.fullmatch(r"m\d+a\d+", ref):
            only, ref = ref, ref.split("a")[0]
        row = db.execute("SELECT * FROM monster WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        out = [_stat_block(row)]
        for a in db.execute(
            "SELECT * FROM monster_power WHERE monster_ref = ? ORDER BY idx", (ref,)
        ):
            if only and a["ref"] != only:
                continue
            # An ability named outright is printed whether or not it is
            # declared: the caller said which row it wanted.
            if not only and not include_all and a["ref"] in declared:
                continue
            kw = json.loads(a["keywords"] or "[]")
            head = (
                f"--- {a['ref']}   {a['section']} / {a['action']} / {a['usage']}"
                + (f" / recharge {a['recharge']}+" if a["recharge"] else "")
                + (f"   keywords: {', '.join(kw)}" if kw else "")
            )
            out.append(f"{head}\n{a['spec']}")
        return "\n\n".join(out)

    return None


def _term(db, ref: str) -> str | None:  # noqa: ANN001
    """A prerequisite clause the parser could not reduce to a mechanic.

    Its text is a deity, a campaign setting's background or a bit of
    publisher's prose, and it is the one thing in the database that may
    never be printed. What can be said is that it exists, what kind of
    thing it is, and how many feats are waiting on it -- which is enough
    to decide whether it is worth building the feature that would answer
    it, and that is the only decision it is wanted for.
    """
    row = db.execute("SELECT * FROM prereq_term WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        return None
    return (
        f"### {row['ref']}   prerequisite term   {row['kind']}   "
        f"asked by {row['uses']} feat{'s' if row['uses'] != 1 else ''}\n"
        "(its text is a printed name and is not printed)"
    )


def _item(db, ref: str, declared: set[str], include_all: bool) -> str | None:  # noqa: ANN001
    """One item's loaded columns, then each block still to be written.

    A block ref asked for by itself gets the same columns above it. The
    numbers are most of what a block needs -- whether the thing is a
    weapon or a neck slot decides half of what its Property can mean --
    and an author handed `i601x1` alone would have gone looking.
    """
    block = None
    if not re.fullmatch(r"i\d+", ref):
        block = db.execute("SELECT * FROM item_block WHERE ref = ?", (ref,)).fetchone()
        if block is None:
            return None
        ref = block["item_ref"]
    row = db.execute("SELECT * FROM item WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        return None
    if block is not None:
        return f"{_item_head(db, row)}\n\n{_block(block)}"

    blocks = db.execute(
        "SELECT * FROM item_block WHERE item_ref = ? ORDER BY idx", (ref,)
    ).fetchall()
    left = [b for b in blocks if include_all or b["ref"] not in declared]
    if blocks and not left:
        return ""
    out = [_item_head(db, row)]
    if row["spec"]:
        out.append(row["spec"])
    out += [_block(b) for b in left]
    return "\n\n".join(out)


def _item_head(db, row) -> str:  # noqa: ANN001
    """The columns, which are loaded from the database and never hand-written.

    The exact analogue of `_stat_block` and it exists for the same reason:
    everything here is already applied by `engine/equipment.py`, so a block
    that restates "+1 to attack and damage" in its body has written the
    bonus twice.

    Only the rungs inside the heroic tier are printed. The ladder runs to
    level 26 and the six rungs of a common weapon filled the line, burying
    the two an author writing heroic content can be handed.
    """
    base = json.loads(row["base"] or "[]")
    lines = [
        f"### {row['ref']}   {row['slot'] or row['category'].lower()}   "
        f"heroic {row['base_level']}{'+' if row['scaling'] else ''}"
        + (f"   {' or '.join(base)}" if base else "")
    ]
    steps = db.execute(
        "SELECT level, plus, cost FROM item_step WHERE ref = ? AND level <= ? "
        "ORDER BY level",
        (row["ref"], MAX_ITEM_LEVEL),
    ).fetchall()
    if steps:
        lines.append("   ".join(_rung(s) for s in steps))
    bonus = []
    if row["enh_to"]:
        bonus.append(f"enhancement: {ENHANCES.get(row['enh_to'], row['enh_to'])}")
    # Four pages print `Critical: None`, and the column holds it verbatim.
    # Printed as-is it reads as a parser that returned nothing.
    if row["crit"] and row["crit"] != "None":
        bonus.append(f"crit: {row['crit']}")
    if bonus:
        lines.append("   ".join(bonus))
    lines.append("(these load from game.db -- do not hand-write them)")
    return "\n".join(lines)


def _rung(step) -> str:  # noqa: ANN001
    """23 heroic ladders have no enhancement bonus at all -- three levels,
    three prices, an empty plus column -- so the plus is printed only
    where there is one, rather than as a `+0` nobody should write."""
    plus = f"+{step['plus']} @ " if step["plus"] else ""
    return f"{plus}level {step['level']} ({step['cost']:,} gp)"


def _block(row) -> str:  # noqa: ANN001
    kw = json.loads(row["keywords"] or "[]")
    parts = [row["kind"], row["usage"], row["action"]]
    head = f"--- {row['ref']}   " + " / ".join(p for p in parts if p)
    if kw:
        head += f"   keywords: {', '.join(kw)}"
    return f"{head}\n{row['spec']}"


def _feat(db, ref: str) -> str | None:  # noqa: ANN001
    """A feat's gate and its Benefit, and not one word about either.

    The gate is the column, not the prose: `chargen.meets` walks the same
    tree, so anything shown here is something the engine can already
    enforce and nothing the author has to restate. A clause shown as `q17`
    is one the parser could not read -- the author learns that a condition
    exists and never learns what it says, which is the whole arrangement.
    """
    row = db.execute("SELECT * FROM feat WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        return None
    card = ref != f"f{row['id']}"
    gate = row
    if card:
        # A card's gate lives on the parent, which is why `prereq` here is
        # null: counting it twice would have doubled every opaque clause.
        gate = db.execute(
            "SELECT * FROM feat WHERE ref = ?", (f"f{row['id']}",)
        ).fetchone() or row
    head = [f"### {row['ref']}", row["tier"].lower() or "untiered"]
    if card:
        head.append(f"card of f{row['id']}")
    tree = json.loads(gate["prereq"]) if gate["prereq"] else None
    if tree:
        head.append(f"requires: {_requires(tree, top=True)}")
    if gate["unparsed"]:
        head.append(f"unparsed: {gate['unparsed']}")
    return "   ".join(head) + "\n" + re.sub(r"^Benefit\s*:\s*", "", row["spec"])


def _requires(node: dict, top: bool = False) -> str:
    """The prerequisite tree on one line. `&` is all of, `|` is any of.

    The connective is the difference between two gates the prose spells
    the same way -- `Fighter or Warlord` against `Fighter, Dex 13` -- so
    it is kept, and an `any` nested in an `all` is bracketed rather than
    run together.
    """
    for joiner, sep in (("all", " & "), ("any", " | ")):
        if joiner in node:
            inner = sep.join(_requires(child) for child in node[joiner])
            return inner if top else f"({inner})"
    return _atom(node)


def _atom(node: dict) -> str:
    """One leaf. Every shape here is an id, a number, or a word the engine
    already says out loud -- `etl/feat.py` builds them that way precisely so
    this function cannot print a name."""
    if "ability" in node:
        return f"{node['ability']}>={node['min']}"
    if "level" in node:
        return f"level>={node['level']}"
    if "class" in node:
        build = node.get("build")
        return f"class {node['class']}" + (f" ({build})" if build else "")
    if "race" in node:
        return f"race {node['race']}"
    if "ref" in node:
        return f"has {node['ref']}"
    if "skill" in node:
        return f"trained {node['skill']}"
    if "source" in node:
        return f"{node['source']} class"
    if "weapon_prof" in node:
        return f"proficient {node['weapon_prof']}"
    if "term" in node:
        return node["term"]
    return "?"


def _stat_block(row) -> str:  # noqa: ANN001
    """The numbers, which are loaded from the database and never hand-written.

    Printed here only so whoever is writing the abilities can see what they
    are working with -- an attack line that reads `+6 vs. AC` makes more sense
    beside a Strength of 14.
    """
    scores = json.loads(row["scores"] or "{}")
    modes = json.loads(row["modes"] or "{}")
    tags = [t for t in (row["role"], row["size"], row["origin"], row["kind"]) if t]
    for flag in ("minion", "elite", "solo", "leader"):
        if row[flag]:
            tags.append(flag)
    lines = [
        f"### {row['ref']}   level {row['level']}   {', '.join(tags)}",
        f"HP {row['hp']}   AC {row['ac']}  Fort {row['fort']}  "
        f"Ref {row['ref_def']}  Will {row['will']}   Init {row['initiative']:+d}",
        f"Speed {row['speed']}"
        + (f" ({', '.join(f'{k} {v}' for k, v in modes.items())})" if modes else ""),
        "  ".join(f"{k.title()} {v}" for k, v in scores.items()),
    ]
    for label, key in (("Resist", "resist"), ("Vulnerable", "vulnerable")):
        values = json.loads(row[key] or "{}")
        if values:
            lines.append(f"{label} " + ", ".join(f"{v} {k}" for k, v in values.items()))
    immune = json.loads(row["immune"] or "[]")
    if immune:
        lines.append("Immune " + ", ".join(immune))
    lines.append("(these numbers load from game.db -- do not hand-write them)")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
