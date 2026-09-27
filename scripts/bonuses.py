#!/usr/bin/env python
"""Does each `c.bonus` say the bonus type its card prints?

    uv run scripts/bonuses.py           report every disagreement
    uv run scripts/bonuses.py --fix     write the card's type into the code
    uv run scripts/bonuses.py --quiet   the counts only

4e's stacking rule is entirely about the *type* of a bonus: two of the same
type do not add, untyped ones do. So a bonus written with the wrong type is
not a cosmetic slip -- it is a number that is silently too big or too small
in every fight, and nothing else in this repository can see it. `audit.py`
asks whether a row does something; this asks whether what it does is the
printed amount.

The check is possible at all because **the card says which**. "power bonus"
appears 604 times across the compendium, plus enhancement, shield, racial
and the rest; 225 specs say "bonus" with no type word, and those are the
untyped ones. So the comparison is between the `kind=` in the code and the
word in front of "bonus" in `power.spec`, and neither side is a judgement.

`--fix` is safe for the same reason: where the card names a type and the
code omits one, there is exactly one right answer to write in. It will not
touch a call that already names a type, and it will not guess for a row
with no compendium entry -- a class feature has no card, so those are
listed for a person instead.
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The bonus types 4e prints. `untyped` is not a word any card uses -- it is
#: what the absence of the others means -- but a row may say it explicitly.
TYPES = (
    "power", "feat", "item", "racial", "proficiency",
    "enhancement", "shield", "untyped",
)

#: Types a card names by their mechanic instead of by the word "bonus".
#: `enhancement` is deliberately **not** here. The others are types a
#: card grants by naming the mechanic -- "your allies have cover" is a
#: cover bonus and never calls itself one. An item's enhancement is
#: granted by `engine/equipment.py` off a column, never by a row, so a
#: card mentioning it is always pointing at the number rather than
#: handing one out.
MECHANICS = ("cover", "shield", "proficiency", "concealment")

#: A type word is printed as "a **power** bonus" or "+2 **item** bonus".
#: The same word after "the" or "equal to the" is an *amount* being
#: pointed at rather than a type being named.
_AS_TYPE = r"(?:\ba\b|\ban\b|[+-]?\d+)\s+{t}\s+bonus\b"


def _names_type(text: str, t: str) -> bool:
    """Does the card name this as a bonus **type**?

    Only `enhancement` needs the stricter reading, and it needs it badly.
    Every other type word appears on a card only as a type; this one is
    also the name of a number that dozens of magic items point at --
    "deal extra damage equal to the enhancement bonus", "add 5 + the
    enhancement bonus of the orb". Read as a type it advised
    `kind="enhancement"` on two cards that plainly print "item bonus",
    and that kind is the one `engine/equipment.py` uses for the item's
    own plus -- so the two would have eaten each other under the
    same-type rule and the item bonus would have been worth nothing, in
    silence.
    """
    if t != "enhancement":
        return bool(re.search(rf"\b{t}\s+bonus\b", text))
    return bool(re.search(_AS_TYPE.format(t=t), text))


#: Calls are found with `ast`, not a regex. The regex here handled one
#: level of nesting, so a `c.bonus(...)` whose gate is a lambda containing
#: a call was skipped entirely and never checked -- one row in sixty-one
#: was wrong that way and the script reported the file clean.
KIND = re.compile(r"""kind=["']([a-z ]+)["']""")

#: `Mods` is also used as a general keyed store, and those keys are not
#: bonuses any card ever gives a type to -- "automatically a critical hit"
#: is not a +N of any kind. Comparing them against the row's printed text
#: reported a correct row as wrong, because the row had two `c.bonus`
#: calls and only the first was the printed bonus.
INTERNAL = {
    "crit_range", "forced", "forcing", "reach", "concealment",
    "no_advantage", "unflankable", "shift", "initiative",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fix", action="store_true", help="write the card's type in")
    ap.add_argument("--quiet", action="store_true", help="counts only")
    args = ap.parse_args()

    cards = _cards()
    wrong, missing, nocard = [], [], []
    for ref, src, path in _rows():
        card = cards.get(ref)
        for text, key in _calls(src):
            if key in INTERNAL:
                continue
            said = KIND.search(text)
            code = said.group(1) if said else ""
            if card is None:
                nocard.append((ref, code or "(default)", path))
                continue
            typed, plain = card
            if not said:
                # No kind written. Correct if the card types nothing -- and
                # also if it prints an untyped bonus somewhere, since this
                # may be that one. The untyped branch below already made
                # that allowance and this one did not, so a mixed card
                # could never be satisfied from either side.
                if typed and not plain:
                    missing.append((ref, sorted(typed)[0], path, text))
            elif code == "untyped":
                # A card can print one typed bonus and one plain one, and
                # comparing every call against the whole row's set of type
                # words made that row unpassable -- the untyped call was
                # measured against the *other* bonus's word. Untyped is
                # right whenever the card says "bonus" with no type
                # somewhere, or types nothing at all.
                if typed and not plain:
                    wrong.append((ref, code, sorted(typed), path))
            elif code not in typed:
                wrong.append((ref, code, sorted(typed) or ["untyped"], path))

    if args.fix:
        return _fix(missing)

    if not args.quiet:
        for ref, code, card, path in wrong:
            print(f"  WRONG   {ref:9} code says {code!r}, the card says {card} -- {path}")
        for ref, want, path, _ in missing:
            print(f"  add     {ref:9} kind={want!r}, which is what the card prints -- {path}")
    print(
        f"\n  {len(wrong)} disagree with the card, {len(missing)} omit a type the "
        f"card names, {len(nocard)} on refs with no card"
    )
    if nocard and not args.quiet:
        by = Counter(r for r, _, _ in nocard)
        print(f"  (no card: {len(by)} refs -- class features and monster abilities,"
              " which print no bonus type and are a judgement)")
    return 1 if wrong or missing else 0


def _granted(text: str, word: str) -> bool:
    """Does the card *give* this, rather than mention it?

    "your allies have cover" grants a cover bonus. "ignores cover", "no
    cover", "the penalty for cover" and "you must be wielding a shield"
    all mention one without granting it, and matching the bare word made
    five correct rows look wrong -- including one where "shield" appeared
    only in the Requirement line.
    """
    for m in re.finditer(rf"\b{word}\b", text):
        # Back to the start of the sentence, not a fixed window. A
        # negation governs a whole list -- "ignores cover **and
        # concealment**" -- so the word that cancels it can be many
        # tokens away, and four correct rows were flagged because the
        # lookbehind stopped short.
        start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start()))
        before = text[start + 1:m.start()]
        if re.search(
            r"\b(ignore|ignores|ignoring|no|without|not|n't|penalt\w*|must|"
            r"requirement|prerequisite|against creatures that have)\b", before
        ):
            continue
        # **"proficiency with that weapon" is a gate, not a grant**, and
        # the negation list above cannot see it: the sentence has no
        # "must" in it, it simply says "you have proficiency with". Every
        # one of the sixty weapon-style feats opens that way, so the day
        # that family was written the checker started advising
        # `kind="proficiency"` on rows whose bonus is plainly untyped.
        #
        # The distinction is the preposition. A type is named *as* a
        # bonus -- "a proficiency bonus" -- and a possession is followed
        # by "with".
        if re.match(r"\s+with\b", text[m.end():]):
            continue
        return True
    return False


def _calls(src: str) -> list[tuple[str, str]]:
    """Every `c.bonus(...)` in a row, with the `what` it modifies.

    Found through `ast` rather than by matching brackets, because a gate
    written as a lambda nests arbitrarily deep and a regex that stopped at
    one level skipped such a call without saying so.
    """
    import ast

    try:
        tree = ast.parse(textwrap.dedent(src))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "bonus"):
            continue
        text = ast.get_source_segment(textwrap.dedent(src), node) or ""
        first = node.args[0] if node.args else None
        key = first.value if isinstance(first, ast.Constant) else ""
        if isinstance(first, ast.Attribute):     # `AC`, `Defense.AC`
            key = first.attr.lower()
        elif isinstance(first, ast.Name):
            key = first.id.lower()
        out.append((text, str(key).lower()))
    return out


def _cards() -> dict[str, tuple[set[str], bool]]:
    """What bonus types each row's printed text names, and whether it also
    prints a bonus with no type word at all."""
    sys.argv = sys.argv[:1]
    from combat_engine.etl.build import game

    out: dict[str, tuple[set[str], bool]] = {}
    # **Every table that holds a spec.** A monster ability prints a bonus
    # type as readily as a power does and its text lives in
    # `monster_power`; reading only `power` left 165 calls looking like
    # they had no card when most of them had one in the other table.
    #
    # Items and feats were the same mistake made a second time, and it
    # was worse: the first wave of 80 feats made 63 `c.bonus` calls and
    # this instrument said nothing at all about any of them -- not
    # "disagrees", not "no card", nothing. A checker that is silent about
    # a whole corpus reads exactly like a checker that approves of it.
    for table in ("power", "monster_power", "class_feature",
                  "item", "item_block", "feat"):
        for ref, spec in game().execute(f"select ref, spec from {table}"):
            text = (spec or "").lower()
            typed = {t for t in TYPES if _names_type(text, t)}
            # Some types are named by their mechanic rather than by the
            # word "bonus": a card says "your allies have cover", never
            # "a cover bonus", and cover is exactly a +2 of that type.
            # Without this the correct `kind="cover"` read as a mistake.
            typed |= {t for t in MECHANICS if _granted(text, t)}
            # A "+2 bonus" with no word in front of it. `\w+ bonus` would
            # match "+2 bonus" via the number, so the test is that some
            # mention of a bonus is *not* preceded by a type word.
            plain = (
                any(
                    not any(m.group(0).startswith(t) for t in TYPES)
                    for m in re.finditer(r"[a-z]+\s+bonus\b", text)
                )
                or bool(re.search(r"[+-]\d+\s+bonus\b", text))
                # "deals 1d8 extra damage" is a number the card gives and
                # never calls a bonus, so it is untyped -- and a row that
                # also prints a typed bonus has one call of each.
                or "extra damage" in text
            )
            out[ref] = (typed, plain)
    return out


def _rows() -> list[tuple[str, str, str]]:
    """Every declared row's source, with the file it lives in."""
    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    out = []
    for ref, p in REGISTRY.items():
        try:
            src = inspect.getsource(p.body)
            where = Path(inspect.getfile(p.body)).relative_to(ROOT)
        except (OSError, TypeError, ValueError):
            continue
        out.append((ref, src, str(where)))
    return out


def _fix(missing: list[tuple[str, str, str, str]]) -> int:
    """Write `kind=` into the calls whose card names a type.

    Edits the text of each call rather than the file wholesale, and only
    where the call has no `kind=` already, so a second run is a no-op.
    """
    edits: dict[str, list[tuple[str, str]]] = {}
    for _ref, want, path, call in missing:
        fixed = call[:-1].rstrip()
        if not fixed.endswith(","):
            fixed += ","
        fixed += f' kind="{want}")'
        edits.setdefault(path, []).append((call, fixed))

    touched = 0
    for path, pairs in edits.items():
        file = ROOT / path
        text = file.read_text()
        before = text
        for call, fixed in pairs:
            text = text.replace(call, fixed)
        if text != before:
            file.write_text(text)
            touched += 1
    print(f"  wrote {sum(len(v) for v in edits.values())} kinds across {touched} files")
    print("  re-run without --fix, then `uv run ruff check --fix .` for the wrapping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
