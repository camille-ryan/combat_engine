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

from .html import detail, labelled, paragraphs, text
from .sanitise import item_spec, scrub

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

        flavour = re.search(r"</h1>\s*<i>(.*?)</i>", body, re.S)
        out.execute(
            "INSERT INTO race VALUES (?,?,?,?)",
            (ref, row["ID"], size, scrub(spec, {name: ref})),
        )
        names[ref] = {
            "name": name,
            "flavour": text(flavour.group(1)) if flavour else "",
        }
        report.races += 1


def items(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Any,
    names: dict[str, dict[str, str]],
) -> None:
    """Heroic magic items, their ladders and their blocks."""
    scores: list[float] = []
    for row in source.execute(
        "SELECT ID, Name, Category, Rarity, LevelSort, Source, Txt FROM Item "
        "WHERE LevelSort BETWEEN 1 AND ? ORDER BY ID",
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
    names[ref] = {"name": name, "flavour": _flavour(body)}
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
        if head:
            names[block_ref] = {"name": head}
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


def _flavour(body: str) -> str:
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
    books head it `Weapon`, `Neck Slot`, `Wondrous Item`, `Divine Boon` and
    28 other ways, so matching by label means keeping a list of 32 phrases
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


def _slot(label: str) -> str:
    low = " ".join(label.lower().split())
    for tail in (" slot", " item"):
        if low.endswith(tail):
            return low[: -len(tail)]
    return low


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
